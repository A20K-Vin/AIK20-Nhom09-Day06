import requests
import json
import os
from pathlib import Path
from typing import Optional, Dict, List, Any, Set
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv
from urllib.parse import urljoin

# ────────────────────────────────────────────────────────────────────────────
# VINMEC BOOKING AGENT (AGENT 2)
# ────────────────────────────────────────────────────────────────────────────

class VinmecBookingAgent:
    """Trợ lý ảo đặt lịch khám tại Vinmec - chuyên xử lý booking, routing, và phân tích chuyên khoa."""
    
    def __init__(self, api_base_url: str = "http://localhost:8000/api", 
                 doctors_data_path: Optional[str] = None,
                 schedule_path: Optional[str] = None):
        self.api_base_url = api_base_url
        self.session = requests.Session()
        self.booking_context = {}
        
        # Initialize OpenAI client
        self.openai_client = self._init_openai_client()
        
        # Load configuration files
        self.system_prompt = self._load_text_file(
            Path(__file__).parent / "prompt2.txt"
        )
        
        self.valid_specialties = self._load_specialties(
            doctors_data_path or Path(__file__).parent.parent / "data" / "doctors_data.json"
        )
        
        self.schedule_data = self._load_json_file(
            schedule_path or Path(__file__).parent.parent.parent / "data" / "schedule.json"
        )
    
    # ────────────────────── INITIALIZATION ────────────────────────
    
    @staticmethod
    def _init_openai_client() -> Optional[OpenAI]:
        """Initialize OpenAI client từ env variable."""
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("⚠️  Warning: OPENAI_API_KEY not found")
            return None
        print("✓ OpenAI API key loaded")
        return OpenAI(api_key=api_key)
    
    @staticmethod
    def _load_json_file(file_path: str | Path) -> Dict:
        """Load JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            print(f"✓ Loaded JSON from {file_path}")
            return content
        except FileNotFoundError:
            print(f"⚠️  JSON file not found: {file_path}")
            return {}
        except Exception as e:
            print(f"⚠️  Error loading JSON: {e}")
            return {}
    
    @staticmethod
    def _load_text_file(file_path: str | Path) -> str:
        """Load text file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"✓ Loaded text from {file_path}")
            return content
        except FileNotFoundError:
            print(f"⚠️  Text file not found: {file_path}")
            return "Bạn là trợ lý đặt lịch khám tại Vinmec."
        except Exception as e:
            print(f"⚠️  Error loading text: {e}")
            return "Bạn là trợ lý đặt lịch khám tại Vinmec."
    
    def _load_specialties(self, data_path: str | Path) -> Set[str]:
        """Tải danh sách chuyên khoa từ doctors_data.json."""
        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                doctors = json.load(f)
            
            specialties = set()
            if isinstance(doctors, list):
                specialties = {doc.get("specialty", "").strip() for doc in doctors if doc.get("specialty")}
            elif isinstance(doctors, dict):
                specialties = {doc.get("specialty", "").strip() for doc in doctors.values() if isinstance(doc, dict) and doc.get("specialty")}
            
            print(f"✓ Loaded {len(specialties)} specialties")
            return specialties
        except FileNotFoundError:
            print(f"⚠️  doctors_data.json not found, using defaults")
            return {"Tim mạch", "Nhi", "Ngoại chấn thương chỉnh hình", "Gây mê - điều trị đau", "Nội khoa", "Sản phụ khoa"}
        except Exception as e:
            print(f"⚠️  Error loading specialties: {e}")
            return set()
    
    # ────────────────────── AI OPERATIONS ────────────────────────
    
    def generate_response(self, user_message: str, context: Optional[Dict] = None) -> str:
        """Generate natural response từ OpenAI dựa trên prompt2 và context."""
        if not self.openai_client:
            return "Xin lỗi, hiện tại tôi không thể xử lý yêu cầu của bạn."
        
        # Build context message
        context_parts = []
        if context:
            if context.get("specialty"):
                context_parts.append(f"Chuyên khoa được chọn: {context['specialty']}")
            if context.get("available_slots"):
                context_parts.append(f"Khung giờ rảnh: {', '.join(context['available_slots'])}")
        
        user_input = "\n".join(context_parts + [user_message]) if context_parts else user_message
        
        try:
            completion = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.7,
                max_tokens=500,
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"⚠️  OpenAI error: {e}")
            return "Xin lỗi, có lỗi khi xử lý yêu cầu của bạn."
    
    def extract_specialty(self, message: str) -> Optional[str]:
        """Trích xuất specialty từ message dùng AI (handle typo)."""
        if not self.openai_client:
            return None
        
        specialty_list = json.dumps(list(self.valid_specialties), ensure_ascii=False)
        prompt = f"""Kiểm tra xem user có nhắc tới chuyên khoa nào từ danh sách này:
{specialty_list}

Nếu sai chính tả, sửa thành tên chính xác. Trả về JSON: {{"found": bool, "specialty": str|null}}"""
        
        try:
            result = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": f"{prompt}\n\nUser message: {message}"}],
                temperature=0.3,
            )
            data = json.loads(result.choices[0].message.content)
            if data.get("found"):
                print(f"✓ Extracted specialty: {data['specialty']}")
                return data.get("specialty")
        except Exception as e:
            print(f"⚠️  Extraction error: {e}")
        return None
    
    def route_to_agent1(self, user_message: str) -> Optional[str]:
        """Route message tới Agent1 để phân tích triệu chứng."""
        try:
            base_url = self.api_base_url.rstrip('/api').rstrip('/')
            chat_url = urljoin(base_url + '/', 'api/chat')
            response = self.session.post(
                chat_url,
                json={"message": user_message},
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                self.booking_context["agent1_response"] = result.get("message")
                specialty = result.get("specialty")
                print(f"✓ Agent1 inferred: {specialty}")
                return specialty
        except Exception as e:
            print(f"⚠️  Agent1 error: {e}")
        return None
    
    # ────────────────────── BOOKING OPERATIONS ────────────────────────
    
    def get_available_slots(self, specialty: str) -> Dict[str, Any]:
        """Lấy danh sách bác sĩ và khung giờ từ schedule.json."""
        if not self.schedule_data.get("hospitals"):
            return {"error": "Schedule not available"}
        
        # Navigate to specialty
        hospital = self.schedule_data["hospitals"].get("1", {})
        for spec_data in hospital.get("specialties", {}).values():
            if spec_data.get("specialty_name") == specialty:
                return self._extract_slots_from_specialty(spec_data, specialty)
        
        return {"error": f"Specialty '{specialty}' not found"}
    
    def _extract_slots_from_specialty(self, spec_data: Dict, specialty: str) -> Dict:
        """Extract slots từ specialty data."""
        slots_data = {}
        
        for doctor_id, doctor_info in spec_data.get("doctors", {}).items():
            doctor_name = doctor_info.get("doctor_name", f"Doctor {doctor_id}")
            slots_list = []
            
            for date_data in doctor_info.get("dates", {}).values():
                if isinstance(date_data, dict):
                    for time_info in date_data.get("times", []):
                        if isinstance(time_info, dict) and time_info.get("time"):
                            slots_list.append(time_info["time"])
            
            if slots_list:
                slots_data[doctor_id] = {"name": doctor_name, "slots": slots_list}
        
        return {"specialty": specialty, "doctors": slots_data, "count": len(slots_data)}
    
    def suggest_appointment_options(self, specialty: str) -> str:
        """Đưa ra gợi ý khung giờ (Sáng/Chiều) cho user."""
        slots_data = self.get_available_slots(specialty)
        
        if "error" in slots_data or not slots_data.get("doctors") or slots_data.get("count", 0) == 0:
            err_msg = slots_data.get("error", "No doctors available")
            return self.generate_response(f"Không có lịch khám: {err_msg}", {"specialty": specialty})
        
        # Organize morning/afternoon slots
        morning_slots, afternoon_slots, all_slots = self._organize_slots(slots_data)
        
        self.booking_context.update({
            "morning_slots": morning_slots,
            "afternoon_slots": afternoon_slots,
            "step": "select_slot"
        })
        
        context = {
            "specialty": specialty,
            "available_slots": [f"{s['slot']} ({s['doctor_name']})" for s in all_slots[:6]]
        }
        
        msg = f"Cần giúp khách hàng chọn khung giờ khám {specialty}. Đưa ra 2 gợi ý (Sáng/Chiều)."
        return self.generate_response(msg, context)
    
    def _organize_slots(self, slots_data: Dict) -> tuple:
        """Group slots thành Sáng/Chiều."""
        morning, afternoon, all_slots = [], [], []
        
        for doctor_id, doctor_info in slots_data["doctors"].items():
            for slot in doctor_info["slots"]:
                slot_obj = {
                    "doctor_id": doctor_id,
                    "doctor_name": doctor_info["name"],
                    "slot": slot
                }
                all_slots.append(slot_obj)
                
                if int(slot.split(":")[0]) < 12:
                    morning.append({**slot_obj, "type": "Sáng"})
                else:
                    afternoon.append({**slot_obj, "type": "Chiều"})
        
        return morning, afternoon, all_slots
    
    def handle_booking_request(self, user_message: str) -> str:
        """Smart booking handler - extract specialty hoặc route tới Agent1."""
        # Try extract specialty from message
        specialty = self.extract_specialty(user_message)
        
        if specialty:
            self.booking_context["specialty"] = specialty
            context = {"specialty": specialty}
            return self.generate_response(
                f"Bạn muốn đặt lịch khám {specialty}. Vui lòng chọn bác sĩ và khung giờ.",
                context
            )
        
        # Route to Agent1
        specialty = self.route_to_agent1(user_message)
        if specialty:
            self.booking_context["specialty"] = specialty
            agent_msg = self.booking_context.get("agent1_response", "")
            return self.generate_response(
                f"Agent1 phân tích: {agent_msg}. Xin vui lòng xác nhận chuyên khoa {specialty}.",
                {"specialty": specialty}
            )
        
        # Fallback
        return self.generate_response(
            "Vui lòng mô tả triệu chứng hoặc vấn đề sức khỏe bạn đang gặp phải."
        )
    
    def final_confirmation(self, doctor_id: str, doctor_name: str, 
                          specialty: str, slot: str, booking_date: str) -> str:
        """Xác nhận cuối cùng trước khi đặt lịch."""
        self.booking_context.update({
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "slot": slot,
            "booking_date": booking_date,
            "step": "final_confirm"
        })
        
        msg = f"Xác nhận lịch khám: BS {doctor_name} ({specialty}), {slot}, {booking_date}. Đúng chưa?"
        context = {
            "specialty": specialty,
            "doctor_name": doctor_name,
            "slot": slot,
            "booking_date": booking_date
        }
        return self.generate_response(msg, context)
    
    def create_booking(self, doctor_id: str, slot: str, booking_date: str) -> str:
        """Tạo lịch hẹn qua API."""
        try:
            data = {
                "doctorId": doctor_id,
                "slot": slot,
                "date": booking_date,
                "userId": self.booking_context.get("user_id", "guest")
            }
            response = self.session.post(f"{self.api_base_url}/appointments", json=data, timeout=5)
            
            if response.status_code in [200, 201]:
                appointment = response.json()
                msg = f"Đặt lịch thành công! BS {appointment.get('doctor')} ({appointment.get('specialty')}), {appointment.get('slot')} {appointment.get('date')}"
                return self.generate_response(msg, {"appointment": appointment})
            else:
                err = response.json().get("detail", "Unknown error")
                return f"❌ Lỗi đặt lịch: {err}"
        except Exception as e:
            return f"❌ Lỗi: {str(e)}"
    
    # ────────────────────── UTILITIES ────────────────────────
    
    def validate_specialty(self, specialty: str) -> bool:
        """Check if specialty valid."""
        if not specialty or not self.valid_specialties:
            return False
        spec_lower = specialty.lower().strip()
        return any(spec_lower == s.lower() or spec_lower in s.lower() for s in self.valid_specialties)
    
    def handle_escalation(self, reason: str) -> str:
        """Xử lý escalation tới nhân viên."""
        return (f"Xin lỗi, tôi không thể xử lý yêu cầu này.\n"
                f"Lý do: {reason}\n"
                f"Sẽ chuyển bạn tới nhân viên tư vấn Vinmec. Vui lòng chờ... ⏳")


# ────────────────────────────────────────────────────────────────────────────
# USAGE EXAMPLE
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    agent = VinmecBookingAgent()
    
    if agent.openai_client is None:
        print("❌ ERROR: OPENAI_API_KEY not found")
        exit(1)
    
    print("="*60)
    print("🏥 VINMEC BOOKING AGENT - DEMO")
    print("="*60 + "\n")
    
    # Demo 1: Handle booking request with specialty mentioned
    user_msg = "Tôi muốn khám tim mạch"
    print(f"👤 User: {user_msg}")
    response = agent.handle_booking_request(user_msg)
    print(f"🤖 Agent: {response}\n")
    
    # Demo 2: Get appointment options
    specialty = "Tim mạch"
    print(f"📋 Getting options for {specialty}...")
    suggestions = agent.suggest_appointment_options(specialty)
    print(f"🤖 {suggestions}\n")
    
    # Demo 3: Confirm booking
    print(f"📋 Final confirmation...")
    confirmation = agent.final_confirmation(
        doctor_id="16039", 
        doctor_name="Trần Trung Dũng",
        specialty=specialty,
        slot="09:00",
        booking_date="15/04/2026"
    )
    print(f"🤖 {confirmation}")
