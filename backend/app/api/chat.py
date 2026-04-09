from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.agent_service import AgentService


router = APIRouter()
agent_service = AgentService()


class ChatRequest(BaseModel):
    # New contract requested by user.
    messages: str = ""

    # Backward compatibility with existing frontend payload.
    message: str = ""
    history: list[dict] = Field(default_factory=list)
    doctor_context: str = ""
    current_step: str | None = ""


class Suggestion(BaseModel):
    name: str = ""
    doctor_name: str = ""
    doctor_url: str = ""
    image: str = ""
    title: str = ""
    specialty: str = ""
    clinic: str = ""
    workplace: str = ""
    rating: float = 0.0
    profile_image_url: str = ""
    profile_image_file: str = ""
    id: str = ""
    slots: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    message: str
    suggestions: list[Suggestion] = Field(default_factory=list)

    # Keep compatibility for current frontend.
    step: str = "analyze"
    doctor_suggestion: list[Suggestion] = Field(default_factory=list)


@router.post("/chat", response_model=ChatResponse)
def post_chat(body: ChatRequest):
    user_text = (body.messages or body.message or "").strip()
    if not user_text:
        return ChatResponse(message="Vui lòng nhập nội dung tin nhắn.", suggestions=[])

    result = agent_service.chat(
        messages=user_text,
        doctor_context=body.doctor_context,
        current_step=body.current_step,
        history=body.history,
    )

    suggestions = result.get("suggestions", [])

    return ChatResponse(
        message=result.get("message", ""),
        suggestions=suggestions,
        step=result.get("step", "analyze"),
        doctor_suggestion=result.get("doctor_suggestion", suggestions),
    )
