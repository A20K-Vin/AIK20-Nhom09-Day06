import importlib.util
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_AGENT_DIR = Path(__file__).resolve().parents[2] / "agent"


def _load_agent_module(name: str):
    """Load agent1 hoặc agent2 trực tiếp từ file, không phụ thuộc sys.path."""
    path = _AGENT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

DEFAULT_SLOTS = ["08:00", "09:30", "14:00", "15:30"]

CONFIRM_SPECIALTY_KEYWORDS = [
    "đồng ý",
    "xác nhận",
    "khoa này",
    "đặt lịch",
    "book",
    "hẹn khám",
]

CONSULT_STAFF_KEYWORDS = [
    "tư vấn",
    "nhân viên",
    "chăm sóc khách hàng",
    "gọi nhân viên",
]


class AgentService:
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.openai_api_key) if self.openai_api_key else None

        self.agent1 = None
        self.agent2 = None
        self.doctors = self._load_doctors()

        try:
            agent1_mod = _load_agent_module("agent1")
            agent2_mod = _load_agent_module("agent2")
            VinmecAgent = agent1_mod.VinmecAgent
            VinmecBookingAgent = agent2_mod.VinmecBookingAgent

            doctors_data_path = str(Path(__file__).resolve().parents[2] / "data" / "doctors_data.json")

            self.agent2 = VinmecBookingAgent(
                api_base_url="http://localhost:8000/api",
                doctors_data_path=doctors_data_path,
            )

            if self.openai_api_key:
                self.agent1 = VinmecAgent(
                    data_json_path=str(_AGENT_DIR / "data" / "medical_knowledge_base.json"),
                    prompt_file_path=str(_AGENT_DIR / "prompt1.txt"),
                    api_key=self.openai_api_key,
                )
        except Exception as e:
            print(f"⚠️  Agent load failed: {e}")
            self.agent1 = None
            self.agent2 = None

    def _load_doctors(self):
        data_path = Path(__file__).resolve().parents[2] / "data" / "doctors_data.json"
        if not data_path.exists():
            return []

        try:
            with open(data_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return []

        doctors = []
        for idx, item in enumerate(raw):
            image_url = item.get("profile_image_url", "")
            doctors.append(
                {
                    "id": f"doc-{idx:04d}",
                    "name": item.get("full_name", ""),
                    "doctor_name": item.get("full_name", ""),
                    "doctor_url": image_url,
                    "image": image_url,
                    "title": item.get("title", ""),
                    "specialty": item.get("specialty", ""),
                    "clinic": item.get("workplace", ""),
                    "workplace": item.get("workplace", ""),
                    "profile_image_url": image_url,
                    "profile_image_file": item.get("profile_image_file", ""),
                    "rating": 4.8,
                    "slots": DEFAULT_SLOTS,
                }
            )
        return doctors

    def _infer_intent(self, message: str) -> str:
        if self.client is None:
            return "symptom"

        prompt = (
            'Phân loại ý định sang: "symptom" (mô tả triệu chứng) hoặc "booking" (đặt lịch hẹn). '
            'Trả JSON: {"intent":"symptom"} hoặc {"intent":"booking"}'
        )
        try:
            completion = self.client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": message},
                ],
                temperature=0.2,
            )
            result = json.loads(completion.choices[0].message.content)
            return result.get("intent", "symptom")
        except Exception:
            return "symptom"

    def _extract_specialty_from_text(self, text: str) -> str:
        if self.agent2 is not None:
            for length in range(40, 2, -1):
                for i in range(len(text) - length + 1):
                    candidate = text[i : i + length].strip()
                    if self.agent2.validate_specialty(candidate):
                        return candidate

        lowered = text.lower()
        for specialty in {d.get("specialty", "") for d in self.doctors}:
            if specialty and specialty.lower() in lowered:
                return specialty

        return "Nội tổng quát"

    def _build_suggestions(self, specialty: str):
        matched = [d for d in self.doctors if d.get("specialty") == specialty]
        others = [d for d in self.doctors if d.get("specialty") != specialty]
        return (matched + others)[:3]

    def _parse_doctor_context(self, doctor_context: str):
        context = {}
        if not doctor_context:
            return context

        for part in doctor_context.split("|"):
            part = part.strip()
            if part.startswith("Chuyên khoa:"):
                context["specialty"] = part.replace("Chuyên khoa:", "").strip()
            if part.startswith("Bác sĩ:"):
                context["doctor_name"] = part.replace("Bác sĩ:", "").strip()
            if part.startswith("Phòng khám:"):
                context["clinic"] = part.replace("Phòng khám:", "").strip()
            if part.startswith("Khung giờ có sẵn:"):
                context["available_slots"] = [
                    s.strip() for s in part.replace("Khung giờ có sẵn:", "").split(",")
                ]
        return context

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        lowered = (text or "").strip().lower()
        return any(keyword in lowered for keyword in keywords)

    def _is_specialty_confirmation(self, message: str) -> bool:
        return self._contains_any(message, CONFIRM_SPECIALTY_KEYWORDS)

    def _is_consult_staff_request(self, message: str) -> bool:
        return self._contains_any(message, CONSULT_STAFF_KEYWORDS)

    def chat(self, messages: str, doctor_context: str = "", current_step: str = "", history=None):
        if self._is_consult_staff_request(messages):
            return {
                "message": "Mình đã ghi nhận yêu cầu tư vấn với nhân viên. Vui lòng giữ máy, bộ phận hỗ trợ sẽ liên hệ sớm.",
                "step": "consult_staff",
                "suggestions": [],
                "doctor_suggestion": [],
            }

        normalized_step = (current_step or "").strip().lower()
        force_booking = normalized_step == "analyze" and self._is_specialty_confirmation(messages)
        intent = "booking" if force_booking else self._infer_intent(messages)

        if intent == "booking" and self.agent2 is not None:
            context = self._parse_doctor_context(doctor_context)
            enhanced = messages
            if context.get("doctor_name"):
                enhanced = f"[Bác sĩ đang được chọn: {context['doctor_name']}] {messages}"
            try:
                reply = self.agent2.generate_response(enhanced, context or None)
            except Exception:
                reply = "Xin lỗi, hiện tại tôi chưa thể xử lý đặt lịch. Vui lòng thử lại sau."

            # Nếu user đã nhập giờ cụ thể → chuyển sang suggest_slot
            has_time = bool(re.search(r"\b\d{1,2}[h:]\d{0,2}\b", messages, re.IGNORECASE))
            next_step = "suggest_slot" if (has_time and normalized_step == "ask_time") else "ask_time"

            return {
                "message": reply,
                "step": next_step,
                "suggestions": [],
                "doctor_suggestion": [],
            }

        if intent == "booking" and self.agent2 is None:
            return {
                "message": "Bạn đã xác nhận chuyên khoa. Vui lòng chọn buổi khám (sáng hoặc chiều) để mình gợi ý khung giờ phù hợp.",
                "step": "ask_time",
                "suggestions": [],
                "doctor_suggestion": [],
            }

        if self.agent1 is not None:
            try:
                reply = self.agent1.handle_request(messages)
            except Exception:
                reply = "Đã ghi nhận triệu chứng của bạn. Dưới đây là gợi ý bác sĩ phù hợp."
        else:
            reply = "Đã ghi nhận triệu chứng của bạn. Dưới đây là gợi ý bác sĩ phù hợp."

        specialty = self._extract_specialty_from_text(reply)
        suggestions = self._build_suggestions(specialty)

        return {
            "message": reply,
            "step": "analyze",
            "suggestions": suggestions,
            "doctor_suggestion": suggestions,
        }
