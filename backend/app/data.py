import json
from pathlib import Path
from typing import Any

# ── Load doctors from JSON ────────────────────────────────────────────────────

_JSON_PATH = Path(__file__).parent.parent / "data" / "doctors_data.json"

_SLOT_TEMPLATES = [
    ["08:00", "09:30", "14:00", "15:30"],
    ["08:30", "10:00", "13:30", "15:00"],
    ["07:45", "09:15", "11:00", "14:30"],
    ["09:00", "10:30", "13:00", "16:00"],
]


def _load_doctors() -> list[dict[str, Any]]:
    with open(_JSON_PATH, encoding="utf-8") as f:
        raw: list[dict] = json.load(f)

    doctors = []
    for i, item in enumerate(raw):
        if not item.get("full_name") or not item.get("specialty"):
            continue
        doctors.append({
            "id": f"doc-{i:04d}",
            "name": item["full_name"],
            "title": item.get("title", ""),
            "specialty": item["specialty"],
            "clinic": item.get("workplace", ""),
            "image": item.get("profile_image_url", ""),
            "slots": _SLOT_TEMPLATES[i % len(_SLOT_TEMPLATES)],
        })
    return doctors


DOCTORS: list[dict[str, Any]] = _load_doctors()

# ── In-memory stores ─────────────────────────────────────────────────────────

# appointments: list of dicts { id, userId, doctorId, slot, date, doctor, specialty }
appointments_store: list[dict[str, Any]] = []

# sessions: list of dicts { id, userId, symptom, summary, time, messages[] }
sessions_store: list[dict[str, Any]] = []
