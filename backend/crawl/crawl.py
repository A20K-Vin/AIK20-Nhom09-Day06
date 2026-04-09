from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
import re


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
        }))
        """
    )

    slots = []
    seen = set()
    for item in slot_nodes:
        class_name = item.get("className") or ""
        if "disable" in class_name or "inactive" in class_name:
            continue

        time_text = extract_first_time_token(item.get("text") or "")
        if not time_text:
            continue

        if time_text in seen:
            continue
        seen.add(time_text)

        slots.append({"id": item.get("id") or "N/A", "time": time_text})

    return slots

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

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
        if hospital_id == "" or hospital_id == "Chọn cơ sở khám":
            continue  
        print(f"Hospital: {hospital_name} (ID: {hospital_id})")
        prev_specialty_signature = get_select_signature(page, "#specialty")
        page.select_option("#hospital", hospital_id)

        try:
            wait_for_select_updated(page, "#specialty", prev_specialty_signature)
        except PlaywrightTimeoutError:
            # Keep flow running even when some hospitals are slow/no data.
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

            # Get list of all options in select id="doctor" for each specialty
            prev_doctor_signature = get_select_signature(page, "#doctor")
            page.select_option("#specialty", spec_value)
            try:
                wait_for_select_updated(page, "#doctor", prev_doctor_signature)
            except PlaywrightTimeoutError:
                pass

            doctor_options = page.locator("#doctor option").all()
            for doc in doctor_options:
                if doc.get_attribute("value") == "" or doc.inner_text() == "Chọn Bác sĩ muốn khám":
                    continue
                doc_value = doc.get_attribute("value")
                doc_text = doc.inner_text()
                print(f"    Doctor Value: {doc_value}, Text: {doc_text}")

                # Get schedule for each doctor
                page.select_option("#doctor", doc_value)
                try:
                    page.wait_for_selector("#date_group .item_date", timeout=7000)
                except PlaywrightTimeoutError:
                    print("        No dates")
                    continue

                dates = page.locator("#date_group .item_date").all()

                for i in range(len(dates)):
                    dates = page.locator("#date_group .item_date").all()
                    date = dates[i]

                    date_value = get_item_value(date)
                    date_text = date.inner_text().replace("\n\n", " ").strip()
                    print(f"        Date Value: {date_value}, Text: {date_text}")

                    previous_table_text = ""
                    try:
                        previous_table_text = page.locator("#time_table").inner_text(timeout=1000)
                    except PlaywrightTimeoutError:
                        previous_table_text = ""


    browser.close()