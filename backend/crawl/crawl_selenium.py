from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import re
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# Timeouts (seconds) — tuned to observed response times (<10s never exceeded)
# ---------------------------------------------------------------------------
SELECT_UPDATE_TIMEOUT   = 5    # Wait for <select> options to reload
DATE_SWITCH_TIMEOUT     = 5    # Wait for active-state on clicked date
TABLE_REFRESH_TIMEOUT   = 3    # Wait for #time_table text to change
SLOTS_RENDER_TIMEOUT    = 4    # Wait for .item_time elements to appear
FIXED_WAIT_FALLBACK_S   = 1.0  # Last-resort sleep when all waits time out
DATE_SELECTOR_TIMEOUT   = 5    # Wait for #date_group .item_date to appear
DATE_CLICK_RETRIES      = 3
POLL_FREQ               = 0.15 # WebDriverWait polling interval (seconds)

VN_TZ      = timezone(timedelta(hours=7))
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "data" / "schedule.json"


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def build_date_key(date_value: str, date_text: str) -> str:
    return f"{normalize_text(date_value)}|{normalize_text(date_text)}"


def extract_ddmm_token(date_text: str) -> str:
    m = re.search(r"\b\d{1,2}\/\d{1,2}\b", date_text or "")
    return m.group(0) if m else ""


def extract_first_time_token(raw_text: str):
    m = re.search(r"\b([01]?\d|2[0-3])[:hH]([0-5]\d)\b", raw_text or "")
    if not m:
        return None
    h, minute = m.groups()
    return f"{int(h):02d}:{minute}"


def get_element_value(el) -> str:
    for attr in ("value", "data-value", "data-id", "id"):
        v = el.get_attribute(attr)
        if v:
            return v
    return "N/A"


def get_select_signature(driver, selector: str) -> str:
    options = driver.find_elements(By.CSS_SELECTOR, f"{selector} option")
    return "||".join(
        f"{(o.get_attribute('value') or '').strip()}|{o.text.strip()}"
        for o in options
    )


def get_current_table_text(driver) -> str:
    """Return current #time_table innerText, or a sentinel if absent/empty."""
    try:
        el = driver.find_element(By.CSS_SELECTOR, "#time_table")
        text = (el.text or "").strip()
        return text if text else "__EMPTY_TABLE__"
    except Exception:
        return "__NO_TABLE__"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_existing_schedule(path: Path) -> dict:
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


def persist_schedule(path: Path, final_data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    final_data["updated_at_vn"] = datetime.now(VN_TZ).isoformat()
    with path.open("w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Date / time helpers
# ---------------------------------------------------------------------------

def parse_date_from_label(date_text: str, now_vn: datetime):
    m = re.search(r"(\d{1,2})\/(\d{1,2})", date_text or "")
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    year = now_vn.year
    try:
        candidate = datetime(year, month, day, tzinfo=VN_TZ).date()
    except ValueError:
        return None
    if candidate < now_vn.date() - timedelta(days=180):
        try:
            candidate = datetime(year + 1, month, day, tzinfo=VN_TZ).date()
        except ValueError:
            return None
    return candidate


def filter_slots_by_vietnam_now(slots: list, date_text: str, now_vn: datetime) -> list:
    target_date = parse_date_from_label(date_text, now_vn)
    if target_date is None or target_date != now_vn.date():
        return slots
    current_minutes = now_vn.hour * 60 + now_vn.minute
    filtered = []
    for slot in slots:
        parts = (slot.get("time") or "").split(":")
        if len(parts) != 2:
            continue
        try:
            if int(parts[0]) * 60 + int(parts[1]) > current_minutes:
                filtered.append(slot)
        except ValueError:
            continue
    return filtered


# ---------------------------------------------------------------------------
# Custom WebDriverWait conditions
# ---------------------------------------------------------------------------

class SelectSignatureChanged:
    """True when the <select> options list differs from prev_signature."""
    def __init__(self, selector: str, prev_signature: str):
        self.selector = selector
        self.prev_signature = prev_signature

    def __call__(self, driver):
        options = driver.find_elements(By.CSS_SELECTOR, f"{self.selector} option")
        sig = "||".join(
            f"{(o.get_attribute('value') or '').strip()}|{o.text.strip()}"
            for o in options
        )
        return sig != self.prev_signature


class DateIndexIsActive:
    """
    True when the .item_date at target_index carries an active CSS class
    (active / selected / current / choose) or aria-selected="true",
    AND that class matches what we expect for the target date.
    Verifying by index prevents a pre-existing active element at a different
    index from causing a false-positive before the page updates.
    """
    def __init__(self, target_index: int, target_date_value: str,
                 target_date_text: str, target_date_token: str):
        self.target_index       = target_index
        self.target_date_value  = normalize_text(target_date_value)
        self.target_date_text   = normalize_text(target_date_text)
        self.target_date_token  = target_date_token

    def __call__(self, driver):
        try:
            nodes = driver.find_elements(By.CSS_SELECTOR, "#date_group .item_date")
            if self.target_index >= len(nodes):
                return False

            el = nodes[self.target_index]
            cls          = (el.get_attribute("class") or "").lower()
            aria_selected = (el.get_attribute("aria-selected") or "").lower()

            is_active = (
                aria_selected == "true"
                or "active"   in cls
                or "selected" in cls
                or "current"  in cls
                or "choose"   in cls
            )
            if not is_active:
                return False

            # Secondary: verify value / text / token matches the target.
            value = get_element_value(el)
            if normalize_text(value) and self.target_date_value:
                return normalize_text(value) == self.target_date_value

            active_text = normalize_text(el.text)
            if active_text == self.target_date_text:
                return True
            if self.target_date_token and \
               extract_ddmm_token(active_text) == self.target_date_token:
                return True

            # No value attr and text is unrecognisable — trust index match.
            return True

        except StaleElementReferenceException:
            return False



class SlotsRendered:
    """
    True when #time_table contains .item_time elements OR its text is
    non-empty and different from previous_text.
    """
    def __init__(self, previous_text: str):
        self.previous_text = previous_text

    def __call__(self, driver):
        try:
            table = driver.find_element(By.CSS_SELECTOR, "#time_table")
            if table.find_elements(By.CSS_SELECTOR, ".item_time"):
                return True
            text = (table.text or "").strip()
            return text != "" and text != self.previous_text
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Core scraping helpers
# ---------------------------------------------------------------------------

def wait_for_select_updated(driver, selector: str, prev_signature: str) -> None:
    WebDriverWait(driver, SELECT_UPDATE_TIMEOUT, poll_frequency=POLL_FREQ).until(
        SelectSignatureChanged(selector, prev_signature)
    )


def get_slots_from_time_table(driver) -> list:
    try:
        table = driver.find_element(By.CSS_SELECTOR, "#time_table")
        table_text = (table.text or "").strip().lower()
    except Exception:
        return []

    if "khong co lich trong" in table_text or "không có lịch trống" in table_text:
        return []

    slot_nodes = driver.find_elements(By.CSS_SELECTOR, "#time_table .item_time")

    slots = []
    seen  = set()
    for idx, el in enumerate(slot_nodes):
        try:
            cls           = (el.get_attribute("class")         or "").lower()
            disabled_attr = (el.get_attribute("disabled")      or "").lower()
            aria_disabled = (el.get_attribute("aria-disabled") or "").lower()
        except StaleElementReferenceException:
            continue

        if (
            "disable"  in cls
            or "inactive" in cls
            or disabled_attr == "disabled"
            or aria_disabled == "true"
        ):
            continue

        time_text = extract_first_time_token(el.text or "")
        if not time_text or time_text in seen:
            continue
        seen.add(time_text)

        data_id = el.get_attribute("data-id") or str(idx)
        slots.append({"id": data_id, "time": time_text})

    return slots


def click_date_and_confirm(driver, date_el, date_value: str,
                           date_text: str, date_index: int):
    """
    Click a date element and confirm the switch via four strategies in order:
      1. Active-state by index (fastest, most reliable)
      2. Table text changed
      3. Slot elements rendered
      4. Fixed fallback sleep (last resort)

    Returns (date_switched: bool, method: str).
    """
    previous_table_text = get_current_table_text(driver)
    date_token          = extract_ddmm_token(date_text)

    for attempt in range(DATE_CLICK_RETRIES):
        try:
            if attempt == 0:
                date_el.click()
            else:
                # Force-click via JS when normal click is intercepted.
                driver.execute_script("arguments[0].click();", date_el)
        except Exception:
            if attempt == DATE_CLICK_RETRIES - 1:
                print("          Could not click date after all retries")
            continue

        # Strategy 1 — active state at target index.
        try:
            WebDriverWait(driver, DATE_SWITCH_TIMEOUT, poll_frequency=POLL_FREQ).until(
                DateIndexIsActive(date_index, date_value, date_text, date_token)
            )
            return True, "active_state"
        except TimeoutException:
            if attempt == DATE_CLICK_RETRIES - 1:
                try:
                    nodes = driver.find_elements(By.CSS_SELECTOR, "#date_group .item_date")
                    classes = [
                        f"{(n.get_attribute('class') or '')}|aria={(n.get_attribute('aria-selected') or '')}"
                        for n in nodes[:5]
                    ]
                    print(f"          Date active-state not confirmed. Classes: {classes}")
                except Exception:
                    print("          Date active-state not confirmed (could not read classes)")


    # Strategy 2 — slot elements rendered.
    try:
        WebDriverWait(driver, SLOTS_RENDER_TIMEOUT, poll_frequency=POLL_FREQ).until(
            SlotsRendered(previous_table_text)
        )
        return True, "slots_rendered"
    except TimeoutException:
        pass

    # Strategy 3 — fixed sleep fallback (table may show same "no slots" text
    # for consecutive dates; nothing to diff against).
    import time as _time
    _time.sleep(FIXED_WAIT_FALLBACK_S)
    return True, "fixed_wait_fallback"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def make_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")
    return webdriver.Chrome(options=opts)


driver   = make_driver()
now_vn   = datetime.now(VN_TZ)
final_data = load_existing_schedule(OUTPUT_PATH)
final_data.setdefault("updated_at_vn", now_vn.isoformat())
final_data.setdefault("hospitals", {})

try:
    driver.get("https://www.vinmec.com/vie/dang-ky-kham/")

    # ---- Hospitals --------------------------------------------------------
    hospital_options = driver.find_elements(By.CSS_SELECTOR, "#hospital option")
    hospital_data = [
        (o.get_attribute("value"), o.text)
        for o in hospital_options
    ]

    for hospital_id, hospital_name in hospital_data[:3]:
        if not hospital_id or hospital_name == "Chọn cơ sở khám":
            continue
        if hospital_name not in (
            "BV ĐKQT Vinmec Times City (Hà Nội)",
            "BV ĐKQT Vinmec Central Park (TP.HCM)",
        ):
            continue

        print(f"Hospital: {hospital_name} (ID: {hospital_id})")

        hospital_entry = final_data["hospitals"].setdefault(
            str(hospital_id),
            {
                "hospital_id":   str(hospital_id),
                "hospital_name": hospital_name,
                "specialties":   {},
            },
        )

        prev_specialty_sig = get_select_signature(driver, "#specialty")
        Select(driver.find_element(By.ID, "hospital")).select_by_value(hospital_id)
        try:
            wait_for_select_updated(driver, "#specialty", prev_specialty_sig)
        except TimeoutException:
            pass

        # ---- Specialties --------------------------------------------------
        specialty_options = driver.find_elements(By.CSS_SELECTOR, "#specialty option")
        specialty_data = [
            (o.get_attribute("value"), o.text)
            for o in specialty_options
            if o.get_attribute("value") not in ("", None)
            and o.text not in ("Chọn chuyên khoa", "Chưa xác định chuyên khoa")
        ]

        for spec_value, spec_text in specialty_data:
            print(f"  Specialty Value: {spec_value}, Text: {spec_text}")

            specialty_entry = hospital_entry["specialties"].setdefault(
                str(spec_value),
                {
                    "specialty_id":   str(spec_value),
                    "specialty_name": spec_text,
                    "doctors":        {},
                },
            )

            prev_doctor_sig = get_select_signature(driver, "#doctor")
            Select(driver.find_element(By.ID, "specialty")).select_by_value(spec_value)
            try:
                wait_for_select_updated(driver, "#doctor", prev_doctor_sig)
            except TimeoutException:
                pass

            # ---- Doctors --------------------------------------------------
            doctor_options = driver.find_elements(By.CSS_SELECTOR, "#doctor option")
            doctor_data = [
                (o.get_attribute("value"), o.text)
                for o in doctor_options
                if o.get_attribute("value") not in ("", None)
                and o.text not in (
                    "Chọn Bác sĩ muốn khám",
                    "Không có bác sĩ nào phù hợp với yêu cầu của bạn",
                )
            ]

            for doc_value, doc_text in doctor_data:
                print(f"    Doctor Value: {doc_value}, Text: {doc_text}")

                doctor_entry = specialty_entry["doctors"].setdefault(
                    str(doc_value),
                    {
                        "doctor_id":   str(doc_value),
                        "doctor_name": doc_text,
                        "dates":       {},
                    },
                )

                Select(driver.find_element(By.ID, "doctor")).select_by_value(doc_value)

                try:
                    WebDriverWait(driver, DATE_SELECTOR_TIMEOUT, poll_frequency=POLL_FREQ).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#date_group .item_date"))
                    )
                except TimeoutException:
                    print("        No dates")
                    continue

                # ---- Dates ------------------------------------------------
                date_elements = driver.find_elements(By.CSS_SELECTOR, "#date_group .item_date")
                num_dates     = len(date_elements)

                for i in range(num_dates):
                    # Re-query every iteration to avoid stale references.
                    date_elements = driver.find_elements(By.CSS_SELECTOR, "#date_group .item_date")
                    if i >= len(date_elements):
                        break
                    date_el = date_elements[i]

                    date_value = get_element_value(date_el)
                    date_text  = normalize_text(date_el.text)
                    print(f"        Date Value: {date_value}, Text: {date_text}")

                    date_switched, confirm_method = click_date_and_confirm(
                        driver, date_el, date_value, date_text, i
                    )

                    if confirm_method not in ("active_state", "table_refreshed", "slots_rendered"):
                        print(f"          Date confirmed via: {confirm_method}")

                    if not date_switched:
                        print("          Date switch ultimately failed; skipping date")
                        continue

                    raw_slots       = get_slots_from_time_table(driver)
                    available_slots = filter_slots_by_vietnam_now(raw_slots, date_text, now_vn)

                    date_key = build_date_key(date_value, date_text)
                    doctor_entry["dates"][date_key] = {
                        "date_value": str(date_value),
                        "date_text":  date_text,
                        "slots":      available_slots,
                    }
                    persist_schedule(OUTPUT_PATH, final_data)

                    if not available_slots:
                        print("          Available slots: none")
                        continue

                    print("          Available slots:")
                    for slot in available_slots:
                        print(f"            - {slot['time']} (slot_id={slot['id']})")

    persist_schedule(OUTPUT_PATH, final_data)

finally:
    driver.quit()