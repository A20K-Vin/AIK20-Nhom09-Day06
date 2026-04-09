from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat as chat_api
from app.routers import doctors, appointments, sessions

app = FastAPI(title="MediFlow API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_api.router, prefix="/api", tags=["chat"])
app.include_router(doctors.router, prefix="/api/doctors", tags=["doctors"])
app.include_router(appointments.router, prefix="/api/appointments", tags=["appointments"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])


@app.get("/")
def root():
    return {"message": "MediFlow API is running"}
