from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
import re
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path


DATE_SWITCH_TIMEOUT_MS = 10000
TABLE_REFRESH_TIMEOUT_MS = 10000
SLOTS_RENDER_TIMEOUT_MS = 10000
DATE_CLICK_RETRIES = 3


def get_item_value(locator):
    for attr in ("value", "data-value", "data-id", "id"):
        v = locator.get_attribute(attr)
        if v:
            return v
    return "N/A"


def get_select_signature(page, selector):
    options = page.locator(f"{selector} option").all()
    return "||".join(
        f"{(opt.get_attribute('value') or '').strip()}|{opt.inner_text().strip()}"
        for opt in options
    )


def wait_for_select_updated(page, selector, prev_signature, timeout=7000):
    page.wait_for_function(
        """
        ({ selector, prevSignature }) => {
            const options = Array.from(document.querySelectorAll(`${selector} option`));
            const signature = options
                .map(o => `${(o.value || '').trim()}|${(o.textContent || '').trim()}`)
                .join('||');
            return signature !== prevSignature;
        }
        """,
        arg={"selector": selector, "prevSignature": prev_signature},
        timeout=timeout,
    )


def wait_for_slots_rendered(page, previous_table_text, timeout=6000):
    page.wait_for_function(
        """
        ({ previousTableText }) => {
            const table = document.querySelector('#time_table');
            if (!table) return false;

            const text = (table.innerText || '').trim();
            const hasSlotElement = table.querySelector(
                '.item_date, .item_time, .item_slot, [data-time], button'
            );

            if (hasSlotElement) return true;
            return text !== '' && text !== previousTableText;
        }
        """,
        arg={"previousTableText": previous_table_text},
        timeout=timeout,
    )


def wait_for_table_refreshed(page, previous_table_text, timeout=4000):
    page.wait_for_function(
        """
        ({ previousTableText }) => {
            const table = document.querySelector('#time_table');
            if (!table) return false;
            const text = (table.innerText || '').trim();
            return text !== previousTableText;
        }
        """,
        arg={"previousTableText": previous_table_text},
        timeout=timeout,
    )


def normalize_text(value):
    return re.sub(r"\s+", " ", (value or "")).strip()


def build_date_key(date_value, date_text):
    return f"{normalize_text(date_value)}|{normalize_text(date_text)}"


def extract_ddmm_token(date_text):
    match = re.search(r"\b\d{1,2}\/\d{1,2}\b", date_text or "")
    return match.group(0) if match else ""


def wait_for_date_selected(page, target_date_value, target_date_text, target_index, timeout=DATE_SWITCH_TIMEOUT_MS):
    target_date_token = extract_ddmm_token(target_date_text)
    page.wait_for_function(
        """
        ({ targetDateValue, targetDateText, targetDateToken, targetIndex }) => {
            const normalize = (v) => (v || '').replace(/\\s+/g, ' ').trim();
            const extractToken = (v) => {
                const m = (v || '').match(/\\b\\d{1,2}\\/\\d{1,2}\\b/);
                return m ? m[0] : '';
            };
            const nodes = Array.from(document.querySelectorAll('#date_group .item_date'));

            // Find all active elements and their indices.
            const activeEntries = nodes
                .map((el, idx) => ({ el, idx }))
                .filter(({ el }) => {
                    const cls = (el.className || '').toLowerCase();
                    const ariaSelected = (el.getAttribute('aria-selected') || '').toLowerCase() === 'true';
                    return (
                        ariaSelected ||
                        cls.includes('active') ||
                        cls.includes('selected') ||
                        cls.includes('current') ||
                        cls.includes('choose')
                    );
                });

            if (activeEntries.length === 0) return false;

            // Primary check: the element at targetIndex must be one of the active ones.
            // This prevents a pre-existing active element at another index from
            // causing a false-positive match before the page updates.
            const targetIsActive = activeEntries.some(({ idx }) => idx === targetIndex);
            if (!targetIsActive) return false;

            // Secondary check: verify active element content/value matches target.
            // Use the first active entry whose index matches targetIndex.
            const { el: active } = activeEntries.find(({ idx }) => idx === targetIndex);

            const value =
                active.getAttribute('value') ||
                active.getAttribute('data-value') ||
                active.getAttribute('data-id') ||
                active.getAttribute('id') ||
                '';
            const activeText = active.innerText || active.textContent || '';

            // If the element carries a value attribute, require it to match.
            if (normalize(value) !== '' && normalize(targetDateValue) !== '') {
                return normalize(value) === normalize(targetDateValue);
            }

            // Otherwise fall back to text / date-token matching.
            if (normalize(activeText) === normalize(targetDateText)) return true;
            if (targetDateToken !== '' && extractToken(activeText) === targetDateToken) return true;

            // If the element has no value and no recognisable text, trust the index match.
            return true;
        }
        """,
        arg={
            "targetDateValue": str(target_date_value),
            "targetDateText": target_date_text,
            "targetDateToken": target_date_token,
            "targetIndex": target_index,
        },
        timeout=timeout,
    )


def extract_first_time_token(raw_text):
    match = re.search(r"\b([01]?\d|2[0-3])[:hH]([0-5]\d)\b", raw_text or "")
    if not match:
        return None
    h, m = match.groups()
    return f"{int(h):02d}:{m}"


def get_slots_from_time_table(page):
    table_text = page.locator("#time_table").inner_text().strip().lower()
    if "khong co lich trong" in table_text or "không có lịch trống" in table_text:
        return []

    slot_nodes = page.locator("#time_table .item_time").evaluate_all(
        """
        (els) => els.map((el, idx) => ({
            id: el.getAttribute('data-id') || String(idx),
            text: (el.innerText || '').trim(),
            className: (el.className || '').toLowerCase(),
            disabledAttr: (el.getAttribute('disabled') || '').toLowerCase(),
            ariaDisabled: (el.getAttribute('aria-disabled') || '').toLowerCase(),
        }))
        """
    )

    slots = []
    seen = set()
    for item in slot_nodes:
        class_name = item.get("className") or ""
        disabled_attr = item.get("disabledAttr") or ""
        aria_disabled = item.get("ariaDisabled") or ""
        if (
            "disable" in class_name
            or "inactive" in class_name
            or disabled_attr == "disabled"
            or aria_disabled == "true"
        ):
            continue

        time_text = extract_first_time_token(item.get("text") or "")
        if not time_text:
            continue

        if time_text in seen:
            continue
        seen.add(time_text)

        slots.append({"id": item.get("id") or "N/A", "time": time_text})

    return slots


VN_TZ = timezone(timedelta(hours=7))
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "data" / "schedule.json"


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


def parse_date_from_label(date_text, now_vn):
    """Parse date text like '09/04 Thu 5' into a date in Vietnam timezone."""
    match = re.search(r"(\d{1,2})\/(\d{1,2})", date_text or "")
    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year = now_vn.year

    try:
        candidate = datetime(year, month, day, tzinfo=VN_TZ).date()
    except ValueError:
        return None

    # Handle year boundary when crawling around New Year.
    if candidate < now_vn.date() - timedelta(days=180):
        try:
            candidate = datetime(year + 1, month, day, tzinfo=VN_TZ).date()
        except ValueError:
            return None

    return candidate


def filter_slots_by_vietnam_now(slots, date_text, now_vn):
    target_date = parse_date_from_label(date_text, now_vn)
    if target_date is None or target_date != now_vn.date():
        return slots

    current_minutes = now_vn.hour * 60 + now_vn.minute
    filtered = []
    for slot in slots:
        time_value = slot.get("time") or ""
        parts = time_value.split(":")
        if len(parts) != 2:
            continue

        try:
            slot_minutes = int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            continue

        if slot_minutes > current_minutes:
            filtered.append(slot)

    return filtered


def get_current_table_text(page, timeout=2000):
    """
    Safely capture the current #time_table innerText.
    Returns a sentinel string when the element is absent or times out,
    so that wait_for_table_refreshed can still detect a genuine change.
    """
    try:
        text = page.locator("#time_table").inner_text(timeout=timeout).strip()
        # Use a sentinel when the table is empty so an actual render is
        # distinguishable from "no change".
        return text if text else "__EMPTY_TABLE__"
    except PlaywrightTimeoutError:
        return "__NO_TABLE__"


def click_date_and_confirm(page, date, date_value, date_text, date_index):
    """
    Click a date element and confirm the switch through several strategies.

    Returns (date_switched: bool, method: str) where method is a short label
    describing how confirmation was obtained (useful for debugging).
    """
    previous_table_text = get_current_table_text(page)

    for click_attempt in range(DATE_CLICK_RETRIES):
        try:
            date.click(force=(click_attempt >= 1))
            page.wait_for_timeout(250)
        except PlaywrightTimeoutError:
            if click_attempt == DATE_CLICK_RETRIES - 1:
                print("          Could not click date after all retries")
            continue

        # Strategy 1: active-class / aria-selected confirmation, verified by index.
        try:
            wait_for_date_selected(
                page,
                date_value,
                date_text,
                date_index,
                timeout=DATE_SWITCH_TIMEOUT_MS,
            )
            return True, "active_state"
        except PlaywrightTimeoutError:
            if click_attempt == DATE_CLICK_RETRIES - 1:
                # Log actual class names to help diagnose future failures.
                try:
                    active_classes = page.locator("#date_group .item_date").evaluate_all(
                        "els => els.map(e => (e.className || '') + '|aria=' + (e.getAttribute('aria-selected') || ''))"
                    )
                    print(f"          Date active-state not confirmed. Classes: {active_classes[:5]}")
                except Exception:
                    print("          Date active-state not confirmed (could not read classes)")

    # Strategy 2: table text changed.
    try:
        wait_for_table_refreshed(page, previous_table_text, timeout=TABLE_REFRESH_TIMEOUT_MS)
        return True, "table_refreshed"
    except PlaywrightTimeoutError:
        pass

    # Strategy 3: slot elements rendered (even if text is same as before).
    try:
        wait_for_slots_rendered(page, previous_table_text, timeout=SLOTS_RENDER_TIMEOUT_MS)
        return True, "slots_rendered"
    except PlaywrightTimeoutError:
        pass

    # Strategy 4: last-resort fixed wait — the page may have updated silently
    # (e.g. table shows same "no slots" text for consecutive dates).
    page.wait_for_timeout(1500)
    return True, "fixed_wait_fallback"


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    now_vn = datetime.now(VN_TZ)
    final_data = load_existing_schedule(OUTPUT_PATH)
    final_data.setdefault("updated_at_vn", now_vn.isoformat())
    final_data.setdefault("hospitals", {})

    page.goto("https://www.vinmec.com/vie/dang-ky-kham/")

    # Get list of all options in select id="hospital"
    options = page.locator("#hospital option").all()
    hospital_data = []
    for opt in options:
        value = opt.get_attribute("value")
        text = opt.inner_text()
        hospital_data.append((value, text))

    # Get list of all options in select id="specialty" for each hospital
    for hospital in hospital_data[:3]:
        hospital_id = hospital[0]
        hospital_name = hospital[1]
        if hospital_id == "" or hospital_name == "Chọn cơ sở khám":
            continue

        if hospital_name != "BV ĐKQT Vinmec Times City (Hà Nội)" and \
                hospital_name != "BV ĐKQT Vinmec Central Park (TP.HCM)":
            continue

        print(f"Hospital: {hospital_name} (ID: {hospital_id})")

        hospital_entry = final_data["hospitals"].setdefault(
            str(hospital_id),
            {
                "hospital_id": str(hospital_id),
                "hospital_name": hospital_name,
                "specialties": {},
            },
        )

        prev_specialty_signature = get_select_signature(page, "#specialty")
        page.select_option("#hospital", hospital_id)

        try:
            wait_for_select_updated(page, "#specialty", prev_specialty_signature)
        except PlaywrightTimeoutError:
            pass

        specialty_options = page.locator("#specialty option").all()
        for spec in specialty_options:
            if spec.get_attribute("value") == "" or \
               spec.inner_text() == "Chọn chuyên khoa" or \
               spec.inner_text() == "Chưa xác định chuyên khoa":
                continue
            spec_value = spec.get_attribute("value")
            spec_text = spec.inner_text()
            print(f"  Specialty Value: {spec_value}, Text: {spec_text}")

            specialty_entry = hospital_entry["specialties"].setdefault(
                str(spec_value),
                {
                    "specialty_id": str(spec_value),
                    "specialty_name": spec_text,
                    "doctors": {},
                },
            )

            prev_doctor_signature = get_select_signature(page, "#doctor")
            page.select_option("#specialty", spec_value)
            try:
                wait_for_select_updated(page, "#doctor", prev_doctor_signature)
            except PlaywrightTimeoutError:
                pass

            doctor_options = page.locator("#doctor option").all()
            for doc in doctor_options:
                if doc.get_attribute("value") == "" or \
                        doc.inner_text() == "Chọn Bác sĩ muốn khám" or \
                        doc.inner_text() == "Không có bác sĩ nào phù hợp với yêu cầu của bạn":
                    continue
                doc_value = doc.get_attribute("value")
                doc_text = doc.inner_text()
                print(f"    Doctor Value: {doc_value}, Text: {doc_text}")

                doctor_entry = specialty_entry["doctors"].setdefault(
                    str(doc_value),
                    {
                        "doctor_id": str(doc_value),
                        "doctor_name": doc_text,
                        "dates": {},
                    },
                )

                page.select_option("#doctor", doc_value)
                try:
                    page.wait_for_selector("#date_group .item_date", timeout=7000)
                except PlaywrightTimeoutError:
                    print("        No dates")
                    continue

                dates = page.locator("#date_group .item_date").all()

                for i in range(len(dates)):
                    # Re-query to avoid stale element references after DOM updates.
                    dates = page.locator("#date_group .item_date").all()
                    date = dates[i]

                    date_value = get_item_value(date)
                    date_text = normalize_text(date.inner_text())
                    print(f"        Date Value: {date_value}, Text: {date_text}")

                    # FIX: capture previous_table_text inside the date loop,
                    # right before clicking, so each iteration has a fresh baseline.
                    # click_date_and_confirm handles this internally now.
                    date_switched, confirm_method = click_date_and_confirm(
                        page, date, date_value, date_text, i
                    )

                    if confirm_method not in ("active_state", "table_refreshed", "slots_rendered"):
                        print(f"          Date confirmed via: {confirm_method}")

                    # FIX: ALWAYS attempt to read slots regardless of confirm_method.
                    # Previously a `continue` here skipped slot extraction entirely
                    # when active-state detection failed, causing missed data for
                    # specialties whose date elements use different CSS class names.
                    if not date_switched:
                        # Should not happen with fixed_wait_fallback, but guard anyway.
                        print("          Date switch ultimately failed; skipping date")
                        continue

                    # Wait for table to settle after the confirmed date switch.
                    previous_table_text = get_current_table_text(page)
                    try:
                        wait_for_table_refreshed(
                            page,
                            previous_table_text,
                            timeout=TABLE_REFRESH_TIMEOUT_MS,
                        )
                    except PlaywrightTimeoutError:
                        try:
                            wait_for_slots_rendered(
                                page,
                                previous_table_text,
                                timeout=SLOTS_RENDER_TIMEOUT_MS,
                            )
                        except PlaywrightTimeoutError:
                            # Table may not have changed (same "no slots" state);
                            # proceed and read whatever is currently rendered.
                            pass

                    raw_slots = get_slots_from_time_table(page)
                    available_slots = filter_slots_by_vietnam_now(raw_slots, date_text, now_vn)

                    date_key = build_date_key(date_value, date_text)
                    doctor_entry["dates"][date_key] = {
                        "date_value": str(date_value),
                        "date_text": date_text,
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
    browser.close()