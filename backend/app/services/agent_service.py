import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

DEFAULT_SLOTS = ["08:00", "09:30", "14:00", "15:30"]


class AgentService:
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.openai_api_key) if self.openai_api_key else None

        self.agent1 = None
        self.agent2 = None
        self.doctors = self._load_doctors()

        # Import backend agents from backend/agent folder.
        self._agent_dir = Path(__file__).resolve().parents[2] / "agent"
        if str(self._agent_dir) not in sys.path:
            sys.path.insert(0, str(self._agent_dir))

        try:
            from agent.agent1 import VinmecAgent
            from agent.agent2 import VinmecBookingAgent

            self.agent2 = VinmecBookingAgent(
                api_base_url="http://localhost:8000/api",
                doctors_data_path=str(Path(__file__).resolve().parents[2] / "data" / "doctors_data.json"),
            )

            if self.openai_api_key:
                self.agent1 = VinmecAgent(
                    data_json_path=str(self._agent_dir / "data" / "medical_knowledge_base.json"),
                    prompt_file_path=str(self._agent_dir / "prompt1.txt"),
                    api_key=self.openai_api_key,
                )
        except Exception:
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
            if part.startswith("Khung giờ có sẵn:"):
                context["available_slots"] = [
                    s.strip() for s in part.replace("Khung giờ có sẵn:", "").split(",")
                ]
        return context

    def chat(self, messages: str, doctor_context: str = ""):
        intent = self._infer_intent(messages)

        if intent == "booking" and self.agent2 is not None:
            context = self._parse_doctor_context(doctor_context)
            try:
                reply = self.agent2.generate_response(messages, context or None)
            except Exception:
                reply = "Xin lỗi, hiện tại tôi chưa thể xử lý đặt lịch. Vui lòng thử lại sau."

            return {
                "message": reply,
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
