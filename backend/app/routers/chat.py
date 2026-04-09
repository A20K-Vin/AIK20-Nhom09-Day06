import os
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

from app.data import DOCTORS

load_dotenv()

router = APIRouter()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Danh sách specialty hợp lệ (khớp với dữ liệu doctors_data.json)
VALID_SPECIALTIES = [
    "Tim mạch", "Hô hấp", "Thần kinh", "Da liễu", "Tiêu hóa",
    "Cơ xương khớp", "Nội tiết", "Nội tổng quát", "Tai - Mũi - Họng",
    "Mắt", "Sản phụ khoa", "Nhi", "Tâm thần", "Tiết niệu",
    "Ung bướu - Xạ trị", "Truyền nhiễm", "Phục hồi chức năng",
    "Răng - Hàm - Mặt", "Y học cổ truyền",
]

SYSTEM_PROMPT = f"""Bạn là trợ lý y tế của phòng khám MediFlow.
Nhiệm vụ của bạn là:
1. Lắng nghe triệu chứng người dùng mô tả.
2. Xác định chuyên khoa phù hợp nhất từ danh sách sau: {json.dumps(VALID_SPECIALTIES, ensure_ascii=False)}.
3. Trả lời thân thiện bằng tiếng Việt, giải thích ngắn gọn tại sao nên khám khoa đó.

Bạn PHẢI trả về JSON với đúng 2 trường:
- "specialty": tên chuyên khoa (phải nằm trong danh sách trên, giữ nguyên dấu)
- "message": câu trả lời thân thiện gửi cho người dùng (1-3 câu)

Ví dụ output:
{{"specialty": "Thần kinh", "message": "Triệu chứng đau đầu và chóng mặt kéo dài của bạn có thể liên quan đến hệ thần kinh. Bạn nên đến khám khoa Thần kinh để được chẩn đoán chính xác."}}"""


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    message: str
    doctor_suggestion: list[dict]


@router.post("", response_model=ChatResponse)
def analyze_symptom(body: ChatRequest):
    """
    Gửi tin nhắn triệu chứng → OpenAI phân tích → trả về message + danh sách bác sĩ.
    """
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": body.message},
            ],
            temperature=0.3,
        )
        result = json.loads(completion.choices[0].message.content)
        specialty = result.get("specialty", "Nội tổng quát")
        reply = result.get("message", "Vui lòng đến khám để được tư vấn thêm.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {str(e)}")

    matched = [d for d in DOCTORS if d["specialty"] == specialty]
    others  = [d for d in DOCTORS if d["specialty"] != specialty]
    doctor_suggestion = (matched + others)[:3]

    return ChatResponse(message=reply, doctor_suggestion=doctor_suggestion)
