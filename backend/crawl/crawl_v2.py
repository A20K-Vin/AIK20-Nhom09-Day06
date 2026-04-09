import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://api2.vinmec.com/api/v1/auto-booking/vinmec"
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "data" / "schedule.json"
VN_TZ = timezone(timedelta(hours=7))
CRAWL_DAYS = 3  # today + next 2 days
REQUEST_TIMEOUT_SEC = 20

WEEKDAY_VI = {
    0: "Thu 2",
    1: "Thu 3",
    2: "Thu 4",
    3: "Thu 5",
    4: "Thu 6",
    5: "Thu 7",
    6: "Chu nhat",
}


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def build_date_key(date_value, date_text):
    return f"{normalize_text(date_value)}|{normalize_text(date_text)}"


def extract_first_time_token(raw_text):
    match = re.search(r"\b([01]?\d|2[0-3])[:hH]([0-5]\d)\b", raw_text or "")
    if not match:
        return None
    h, m = match.groups()
    return f"{int(h):02d}:{m}"


def extract_time_from_start_time(start_time_value):
    """Parse API start_time (ISO) and return HH:MM."""
    if not start_time_value:
        return None

    text = str(start_time_value).strip()
    if not text:
        return None

    # Handle both naive ISO and Z-suffixed UTC timestamps.
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%H:%M")
    except ValueError:
        return extract_first_time_token(text)


def load_existing_schedule(path):
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def persist_schedule(path, final_data):
    path.parent.mkdir(parents=True, exist_ok=True)
    final_data["updated_at_vn"] = datetime.now(VN_TZ).isoformat()
    with path.open("w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)


def http_get_json(path, params=None):
    query = f"?{urlencode(params)}" if params else ""
    url = f"{BASE_URL}{path}{query}"

    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="GET",
    )

    with urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as res:
        raw = res.read().decode("utf-8")
        return json.loads(raw)


def extract_items(payload):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    # Common API wrapper keys
    for key in ("results", "data", "items", "result", "payload", "content"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = extract_items(value)
            if nested:
                return nested

    # Fallback: first list in dict
    for value in payload.values():
        if isinstance(value, list):
            return value

    return []


def pick_first(item, keys, default=""):
    for key in keys:
        if key in item and item.get(key) not in (None, ""):
            return item.get(key)
    return default


def to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y"):
        return True
    if text in ("0", "false", "no", "n"):
        return False
    return None


def parse_slot(slot_item):
    slot_id = pick_first(slot_item, ["id", "slot_id", "time_slot_id", "ab_time_slot_id"])

    # Priority 1: use start_time from API response (authoritative field).
    start_time_raw = pick_first(slot_item, ["start_time"])
    time_text = extract_time_from_start_time(start_time_raw)

    # Priority 2: fallback for other APIs/legacy formats.
    if not time_text:
        time_raw = pick_first(
            slot_item,
            ["time", "time_from", "from_time", "slot", "label", "name"],
        )
        time_text = extract_first_time_token(str(time_raw))

    if not time_text and isinstance(slot_item.get("time_slot"), dict):
        nested = slot_item["time_slot"]
        nested_start_time = pick_first(nested, ["start_time"])
        time_text = extract_time_from_start_time(nested_start_time)

    if not time_text and isinstance(slot_item.get("time_slot"), dict):
        time_raw = pick_first(
            slot_item["time_slot"],
            ["time", "time_from", "from_time", "slot", "label", "name"],
        )
        time_text = extract_first_time_token(str(time_raw))

    if not time_text:
        return None

    status = str(slot_item.get("status", "")).strip().lower()
    if status in ("booked", "full", "disabled", "inactive", "closed"):
        return None

    # API has typo field: is_avaiable.
    is_available = to_bool(
        pick_first(slot_item, ["is_available", "is_avaiable", "available"], default=None)
    )
    if is_available is False:
        return None

    is_booked = to_bool(slot_item.get("is_booked"))
    if is_booked is True:
        return None

    is_overdue = to_bool(slot_item.get("is_overdue"))
    if is_overdue is True:
        return None

    enabled = to_bool(slot_item.get("enabled"))
    if enabled is False:
        return None

    canceled = to_bool(slot_item.get("canceled"))
    if canceled is True:
        return None

    disabled = to_bool(slot_item.get("disabled"))
    if disabled is True:
        return None

    remaining = slot_item.get("remaining")
    if isinstance(remaining, int) and remaining <= 0:
        return None

    return {
        "id": str(slot_id) if slot_id not in (None, "") else "N/A",
        "time": time_text,
    }


def filter_slots_by_vietnam_now(slots, date_obj, now_vn):
    if date_obj != now_vn.date():
        return slots

    current_minutes = now_vn.hour * 60 + now_vn.minute
    filtered = []
    for slot in slots:
        hh, mm = slot["time"].split(":")
        slot_minutes = int(hh) * 60 + int(mm)
        if slot_minutes > current_minutes:
            filtered.append(slot)
    return filtered


def build_date_label(date_obj):
    return f"{date_obj.strftime('%d/%m')} {WEEKDAY_VI[date_obj.weekday()]}"


def crawl():
    now_vn = datetime.now(VN_TZ)

    final_data = load_existing_schedule(OUTPUT_PATH)
    final_data.setdefault("updated_at_vn", now_vn.isoformat())
    final_data.setdefault("hospitals", {})

    places_payload = http_get_json("/vinmec-place/")
    places = extract_items(places_payload)

    for place in places:
        place_id = pick_first(place, ["id", "vinmec_place_id", "place_id"])
        place_name = pick_first(place, ["name", "vinmec_place_name", "title"], default=f"Place {place_id}")

        if place_id in (None, ""):
            continue

        print(f"Hospital: {place_name} (ID: {place_id})")

        hospital_entry = final_data["hospitals"].setdefault(
            str(place_id),
            {
                "hospital_id": str(place_id),
                "hospital_name": place_name,
                "specialties": {},
            },
        )

        specialties_payload = http_get_json(
            "/doctor-speciality/",
            params={"vinmec_place_id": place_id},
        )
        specialties = extract_items(specialties_payload)

        for spec in specialties:
            spec_id = pick_first(
                spec,
                ["id", "ab_doctor_speciality_id", "doctor_speciality_id", "speciality_id"],
            )
            spec_name = pick_first(spec, ["name", "speciality_name", "title"], default=f"Specialty {spec_id}")

            if spec_id in (None, ""):
                continue

            print(f"  Specialty Value: {spec_id}, Text: {spec_name}")

            specialty_entry = hospital_entry["specialties"].setdefault(
                str(spec_id),
                {
                    "specialty_id": str(spec_id),
                    "specialty_name": spec_name,
                    "doctors": {},
                },
            )

            doctors_payload = http_get_json(
                "/ab-doctor/",
                params={
                    "ab_doctor_speciality_id": spec_id,
                    "vinmec_place_id": place_id,
                },
            )
            doctors = extract_items(doctors_payload)

            for doctor in doctors:
                doctor_id = pick_first(doctor, ["doctor_id", "id", "ab_doctor_id"])
                doctor_name = pick_first(doctor, ["name", "doctor_name", "full_name"], default=f"Doctor {doctor_id}")

                if doctor_id in (None, ""):
                    continue

                print(f"    Doctor Value: {doctor_id}, Text: {doctor_name}")

                doctor_entry = specialty_entry["doctors"].setdefault(
                    str(doctor_id),
                    {
                        "doctor_id": str(doctor_id),
                        "doctor_name": doctor_name,
                        "dates": {},
                    },
                )

                for day_offset in range(CRAWL_DAYS):
                    target_date = now_vn.date() + timedelta(days=day_offset)
                    date_param = target_date.strftime("%Y-%m-%d")
                    date_text = build_date_label(target_date)
                    date_value = str(day_offset)

                    print(f"        Date Value: {date_value}, Text: {date_text}")

                    slots_payload = http_get_json(
                        "/ab-time-slot/",
                        params={
                            "doctor_id": doctor_id,
                            "doctor_speciality_id": spec_id,
                            "vinmec_place_id": place_id,
                            "date": date_param,
                        },
                    )
                    raw_slots = extract_items(slots_payload)

                    seen = set()
                    parsed_slots = []
                    for raw in raw_slots:
                        if not isinstance(raw, dict):
                            continue
                        slot = parse_slot(raw)
                        if not slot:
                            continue
                        if slot["time"] in seen:
                            continue
                        seen.add(slot["time"])
                        parsed_slots.append(slot)

                    available_slots = filter_slots_by_vietnam_now(parsed_slots, target_date, now_vn)

                    date_key = build_date_key(date_value, date_text)
                    doctor_entry["dates"][date_key] = {
                        "date_value": date_value,
                        "date_text": date_text,
                        "api_date": date_param,
                        "slots": available_slots,
                    }
                    persist_schedule(OUTPUT_PATH, final_data)

                    if not available_slots:
                        print("          Available slots: none")
                        continue

                    print("          Available slots:")
                    for slot in available_slots:
                        print(f"            - {slot['time']} (slot_id={slot['id']})")

    persist_schedule(OUTPUT_PATH, final_data)


if __name__ == "__main__":
    crawl()
