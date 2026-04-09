import os
import json
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

from app.data import DOCTORS

load_dotenv()

router = APIRouter()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Import 2 agent ─────────────────────────────────────────────────────────────

_AGENT_DIR = Path(__file__).parent.parent.parent.parent / "agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from agent1 import VinmecAgent          # phân tích triệu chứng (RAG)
from agent2 import VinmecBookingAgent   # điều phối đặt lịch

_agent1 = VinmecAgent(
    data_json_path   = str(_AGENT_DIR / "data" / "medical_knowledge_base.json"),
    prompt_file_path = str(_AGENT_DIR / "prompt1.txt"),
    api_key          = os.getenv("OPENAI_API_KEY"),
)

_agent2 = VinmecBookingAgent(
    api_base_url      = "http://localhost:8000/api",
    doctors_data_path = str(_AGENT_DIR.parent / "backend" / "data" / "doctors_data.json"),
)

# ── Helper: tìm specialty từ text trả về của agent1 ───────────────────────────

def _extract_specialty(text: str) -> str:
    for length in range(40, 2, -1):
        for i in range(len(text) - length + 1):
            candidate = text[i:i + length].strip()
            if _agent2.validate_specialty(candidate):
                return candidate
    return "Nội tổng quát"

# ── Infer intent (giữ nguyên) ─────────────────────────────────────────────────

def _infer_intent(message: str) -> str:
    """
    AI infer intent của user message: 'symptom' hoặc 'booking'
    """
    intent_prompt = """Phân loại ý định sang: "symptom" (mô tả triệu chứng) hoặc "booking" (đặt lịch hẹn)
Trả về JSON: {"intent": "symptom"} hoặc {"intent": "booking"}"""

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": intent_prompt},
                {"role": "user", "content": message},
            ],
            temperature=0.3,
        )
        result = json.loads(completion.choices[0].message.content)
        return result.get("intent", "symptom")
    except:
        return "symptom"


# ── Schema ─────────────────────────────────────────────────────────────────────

class MessageHistory(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[MessageHistory] = []
    doctor_context: str = ""
    current_step: str = ""


class ChatResponse(BaseModel):
    message: str
    step: str
    doctor_suggestion: list[dict]


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post("", response_model=ChatResponse)
def analyze_symptom(body: ChatRequest):
    """
    Gửi tin nhắn → AI infer intent → route sang Agent 1 (triệu chứng) hoặc Agent 2 (đặt lịch).
    """
    intent = _infer_intent(body.message)

    # ── Intent: booking → Agent 2 xử lý hội thoại đặt lịch ──────────────────
    if intent == "booking":
        context = {}
        if body.doctor_context:
            for part in body.doctor_context.split("|"):
                part = part.strip()
                if part.startswith("Chuyên khoa:"):
                    context["specialty"] = part.replace("Chuyên khoa:", "").strip()
                if part.startswith("Khung giờ có sẵn:"):
                    context["available_slots"] = [
                        s.strip() for s in part.replace("Khung giờ có sẵn:", "").split(",")
                    ]

        try:
            reply = _agent2.generate_response(body.message, context or None)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Agent 2 error: {e}")

        return ChatResponse(message=reply, step="ask_time", doctor_suggestion=[])

    # ── Intent: symptom → Agent 1 phân tích triệu chứng ─────────────────────
    try:
        reply = _agent1.handle_request(body.message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Agent 1 error: {e}")

    specialty = _extract_specialty(reply)
    matched   = [d for d in DOCTORS if d["specialty"] == specialty]
    others    = [d for d in DOCTORS if d["specialty"] != specialty]
    doctor_suggestion = (matched + others)[:3]

    return ChatResponse(message=reply, step="analyze", doctor_suggestion=doctor_suggestion)
