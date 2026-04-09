import uuid
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Any

from app.data import sessions_store

router = APIRouter()


class MessageModel(BaseModel):
    sender: str       # "user" | "bot"
    text: str
    withActions: bool = False


class SessionCreateRequest(BaseModel):
    userId: str = "guest"
    symptom: str
    summary: str = "Dang tu van."
    time: str = "Vua xong"
    messages: list[MessageModel] = []


class SessionUpdateRequest(BaseModel):
    symptom: str | None = None
    summary: str | None = None
    time: str | None = None
    messages: list[MessageModel] | None = None


@router.post("", status_code=201)
def create_session(body: SessionCreateRequest):
    """Create a new chat session."""
    session: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "userId": body.userId,
        "symptom": body.symptom,
        "summary": body.summary,
        "time": body.time,
        "messages": [m.model_dump() for m in body.messages],
    }
    sessions_store.append(session)
    return session


@router.get("")
def get_sessions(userId: str = Query(default="guest")):
    """Return all chat sessions for a user."""
    return [s for s in sessions_store if s["userId"] == userId]


@router.patch("/{session_id}")
def update_session(session_id: str, body: SessionUpdateRequest):
    """Update summary, symptom, time or messages of a session."""
    session = next((s for s in sessions_store if s["id"] == session_id), None)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if body.symptom is not None:
        session["symptom"] = body.symptom
    if body.summary is not None:
        session["summary"] = body.summary
    if body.time is not None:
        session["time"] = body.time
    if body.messages is not None:
        session["messages"] = [m.model_dump() for m in body.messages]

    return session
