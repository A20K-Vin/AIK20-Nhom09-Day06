from fastapi import APIRouter, HTTPException, Query

from app.data import DOCTORS

router = APIRouter()


@router.get("")
def get_doctors(specialty: str | None = Query(default=None)):
    """Return all doctors, optionally filtered by specialty."""
    if specialty:
        return [d for d in DOCTORS if d["specialty"] == specialty]
    return DOCTORS


@router.get("/{doctor_id}")
def get_doctor(doctor_id: str):
    """Return a single doctor by ID."""
    doctor = next((d for d in DOCTORS if d["id"] == doctor_id), None)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor


@router.get("/{doctor_id}/slots")
def get_slots(doctor_id: str):
    """Return available time slots for a doctor."""
    doctor = next((d for d in DOCTORS if d["id"] == doctor_id), None)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return {"doctorId": doctor_id, "slots": doctor["slots"]}
