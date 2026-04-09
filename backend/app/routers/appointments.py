import uuid
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.data import DOCTORS, appointments_store

router = APIRouter()


class AppointmentRequest(BaseModel):
    doctorId: str
    slot: str
    date: str          # "DD/MM/YYYY"
    userId: str = "guest"


@router.post("", status_code=201)
def create_appointment(body: AppointmentRequest):
    """Confirm and persist an appointment."""
    doctor = next((d for d in DOCTORS if d["id"] == body.doctorId), None)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    if body.slot not in doctor["slots"]:
        raise HTTPException(status_code=400, detail="Slot not available for this doctor")

    appointment = {
        "id": str(uuid.uuid4()),
        "userId": body.userId,
        "doctorId": body.doctorId,
        "doctor": doctor["name"],
        "specialty": doctor["specialty"],
        "slot": body.slot,
        "date": body.date,
    }
    appointments_store.append(appointment)
    return appointment


@router.get("")
def get_appointments(userId: str = Query(default="guest")):
    """Return all appointments for a user."""
    return [a for a in appointments_store if a["userId"] == userId]


@router.delete("/{appointment_id}", status_code=204)
def delete_appointment(appointment_id: str):
    """Cancel an appointment."""
    for i, a in enumerate(appointments_store):
        if a["id"] == appointment_id:
            appointments_store.pop(i)
            return
    raise HTTPException(status_code=404, detail="Appointment not found")
