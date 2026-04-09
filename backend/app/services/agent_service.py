import importlib.util
import json
import os
import re
import sys
import unicodedata
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

GREETING_KEYWORDS = [
    "hi",
    "hello",
    "xin chào",
    "chào",
    "hey",
]


class AgentService:
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.openai_api_key) if self.openai_api_key else None

        self.agent1 = None
        self.agent2 = None
        self.doctors = self._load_doctors()
        self.specialties = sorted(
            {(d.get("specialty", "") or "").strip() for d in self.doctors if d.get("specialty")}
        )

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
        if self._contains_any(message, GREETING_KEYWORDS):
            return "greeting"

        if self.client is None:
            return "symptom"

        prompt = (
            'Phân loại ý định sang: "symptom" (mô tả triệu chứng), '
            '"booking" (đặt lịch hẹn) hoặc "greeting" (chào hỏi/small talk). '
            'Trả JSON: {"intent":"symptom"} hoặc {"intent":"booking"} hoặc {"intent":"greeting"}'
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
            intent = result.get("intent", "symptom")
            if intent in {"symptom", "booking", "greeting"}:
                return intent
            return "symptom"
        except Exception:
            return "symptom"

    def _normalize_text(self, text: str) -> str:
        text = (text or "").strip().lower()
        normalized = unicodedata.normalize("NFD", text)
        without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        without_marks = without_marks.replace("đ", "d")
        without_marks = re.sub(r"[^a-z0-9\s]", " ", without_marks)
        return re.sub(r"\s+", " ", without_marks).strip()

    def _normalize_time_slot(self, value: str) -> str:
        normalized = self._normalize_text(value)
        match = re.search(r"\b(\d{1,2})\s*(?:h|:)?\s*(\d{0,2})\b", normalized)
        if not match:
            return ""

        hour = int(match.group(1))
        minute_raw = match.group(2) or "00"
        minute = int(minute_raw) if minute_raw.isdigit() else 0
        if hour > 23 or minute > 59:
            return ""
        return f"{hour:02d}:{minute:02d}"

    def _extract_requested_time(self, message: str) -> str | None:
        slot = self._normalize_time_slot(message)
        return slot or None

    def _build_symptom_response(self, symptom_text: str, specialty: str) -> str:
        concern_by_specialty = {
            "Tiêu hóa": "chướng bụng, đầy hơi hoặc các vấn đề tiêu hóa khác",
            "Nội Tiêu hoá - Nội soi": "chướng bụng, đầy hơi hoặc các vấn đề tiêu hóa khác",
            "Tim mạch": "rối loạn huyết áp, rối loạn nhịp tim hoặc các vấn đề tim mạch khác",
            "Hô hấp": "viêm đường hô hấp, kích ứng phế quản hoặc các vấn đề hô hấp khác",
            "Thần kinh": "rối loạn thần kinh, đau đầu kéo dài hoặc các vấn đề thần kinh khác",
        }
        concern = concern_by_specialty.get(specialty, "một số vấn đề sức khỏe liên quan")

        return (
            "Dạ, Vinmec xin chào Anh/Chị. Rất vui được hỗ trợ Anh/Chị trong việc chăm sóc sức khỏe. "
            f"Anh/Chị đang gặp phải triệu chứng {symptom_text}, có thể liên quan đến một số vấn đề như {concern}.\n\n"
            f"Vinmec kính mời Anh/Chị đến thăm khám cùng các chuyên gia tại Khoa {specialty} để được kiểm tra kỹ lưỡng nhất ạ.\n\n"
            "Để Anh/Chị không phải chờ đợi lâu khi đến viện, Anh/Chị dự định thăm khám vào ngày nào và khung giờ nào thuận tiện nhất ạ? "
            "Em sẽ hỗ trợ kiểm tra lịch bác sĩ và đặt hẹn cho Anh/Chị ngay ạ."
        )

    def _canonical_specialty_aliases(self) -> dict[str, str]:
        aliases = {
            "tieu hoa": "Tiêu hóa",
            "noi tieu hoa": "Nội Tiêu hoá - Nội soi",
            "noi tieu hoa noi soi": "Nội Tiêu hoá - Nội soi",
            "gan mat tuy": "Gan - Mật - Tụy",
            "tim mach": "Tim mạch",
            "noi tim mach": "Nội Tim mạch",
            "ho hap": "Hô hấp",
            "than kinh": "Thần kinh",
            "noi than kinh": "Nội Thần kinh",
        }
        return aliases

    def _extract_specialty_from_text(self, text: str) -> str | None:
        if self.agent2 is not None:
            for length in range(40, 2, -1):
                for i in range(len(text) - length + 1):
                    candidate = text[i : i + length].strip()
                    if self.agent2.validate_specialty(candidate):
                        return candidate

        normalized_text = self._normalize_text(text)
        if not normalized_text:
            return None

        for alias, canonical in self._canonical_specialty_aliases().items():
            if alias in normalized_text:
                return canonical

        for specialty in sorted(self.specialties, key=len, reverse=True):
            if self._normalize_text(specialty) in normalized_text:
                return specialty

        return None

    def _infer_specialty_from_symptom(self, message: str, llm_reply: str) -> str | None:
        fallback_keywords = {
            "Tiêu hóa": ["dau bung", "da day", "buon non", "non", "tieu chay", "tao bon"],
            "Hô hấp": ["ho", "kho tho", "dau hong", "sot", "viem hong"],
            "Tim mạch": ["dau nguc", "hoi hop", "danh trong nguc", "tang huyet ap"],
            "Thần kinh": ["dau dau", "chong mat", "te tay chan", "mat ngu"],
        }

        merged_text = self._normalize_text(f"{message} {llm_reply}")
        for specialty, keywords in fallback_keywords.items():
            if any(keyword in merged_text for keyword in keywords):
                return specialty

        if self.client is None or not self.specialties:
            return None

        prompt = (
            "Bạn là bộ phân loại chuyên khoa từ triệu chứng. "
            "Chỉ chọn MỘT chuyên khoa phù hợp nhất từ danh sách cho trước hoặc null nếu không đủ thông tin. "
            'Trả về JSON dạng {"specialty":"..."} hoặc {"specialty":null}.'
        )
        try:
            completion = self.client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"{prompt}\nDanh sách chuyên khoa hợp lệ: {json.dumps(self.specialties, ensure_ascii=False)}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Triệu chứng người dùng: {message}\nPhản hồi mô tả của trợ lý: {llm_reply}",
                    },
                ],
                temperature=0,
            )
            result = json.loads(completion.choices[0].message.content)
            raw_specialty = result.get("specialty")
            if isinstance(raw_specialty, str) and raw_specialty.strip():
                specialty = raw_specialty.strip()
                if specialty in self.specialties:
                    return specialty
                return self._extract_specialty_from_text(specialty)
            return None
        except Exception:
            return None

    def _build_suggestions(self, specialty: str | None):
        if not specialty:
            return []

        normalized_target = self._normalize_text(specialty)
        matched = []
        for doctor in self.doctors:
            doctor_specialty = (doctor.get("specialty", "") or "").strip()
            normalized_doctor_specialty = self._normalize_text(doctor_specialty)
            if not normalized_doctor_specialty:
                continue
            if (
                normalized_doctor_specialty == normalized_target
                or normalized_target in normalized_doctor_specialty
                or normalized_doctor_specialty in normalized_target
            ):
                matched.append(doctor)

        if not matched:
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

    def _handle_manual_time_selection(self, message: str, doctor_context: str):
        context = self._parse_doctor_context(doctor_context)
        available_slots = context.get("available_slots", [])
        requested_slot = self._extract_requested_time(message)
        if not requested_slot or not available_slots:
            return None

        normalized_available = {}
        for slot in available_slots:
            normalized = self._normalize_time_slot(slot)
            if normalized:
                normalized_available[normalized] = slot

        if requested_slot in normalized_available:
            doctor_name = context.get("doctor_name", "bác sĩ đã chọn")
            specialty = context.get("specialty", "chuyên khoa phù hợp")
            clinic = context.get("clinic", "Vinmec")
            return {
                "message": (
                    "Đã xác nhận lịch thành công!\n"
                    f"Bác sĩ: {doctor_name}\n"
                    f"Chuyên khoa: {specialty}\n"
                    f"Thời gian: {requested_slot}\n"
                    f"Phòng khám: {clinic}"
                ),
                "step": "confirmed",
                "suggestions": [],
                "doctor_suggestion": [],
            }

        return {
            "message": (
                f"Khung giờ {requested_slot} hiện chưa có sẵn cho bác sĩ đã chọn. "
                f"Bạn vui lòng chọn một khung giờ khác trong các giờ còn trống: {', '.join(available_slots)}."
            ),
            "step": "ask_time",
            "suggestions": [],
            "doctor_suggestion": [],
        }

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
        if normalized_step in {"ask_time", "suggest_slot"}:
            manual_slot_result = self._handle_manual_time_selection(messages, doctor_context)
            if manual_slot_result is not None:
                return manual_slot_result

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

        if intent == "greeting":
            return {
                "message": "Xin chào! Bạn hãy mô tả triệu chứng để mình tìm chuyên khoa và bác sĩ phù hợp nhé.",
                "step": "ask_symptom",
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
        if not specialty:
            specialty = self._infer_specialty_from_symptom(messages, reply)
        if not specialty:
            specialty = "Nội tổng quát"
        suggestions = self._build_suggestions(specialty)
        symptom_reply = self._build_symptom_response(messages.strip(), specialty)

        return {
            "message": symptom_reply,
            "step": "analyze",
            "suggestions": suggestions,
            "doctor_suggestion": suggestions,
        }
