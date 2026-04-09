import requests
import json
import os
from pathlib import Path
from typing import Optional, Dict, List, Any, Set
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv

# ────────────────────────────────────────────────────────────────────────────
# VINMEC BOOKING AGENT (AGENT 2)
# ────────────────────────────────────────────────────────────────────────────

class VinmecBookingAgent:
    """
    Trợ lý ảo chuyên trách điều phối và đặt lịch hẹn tại Hệ thống Y tế Vinmec.
    
    Chuyên gia vận hành quy trình đặt lịch, am hiểu sơ đồ tổ chức các chuyên khoa
    và điều phối thời gian thực.
    """
    
    def __init__(self, api_base_url: str = "http://localhost:8000/api", 
                 doctors_data_path: Optional[str] = None,
                 backend_env_path: Optional[str] = None):
        self.api_base_url = api_base_url
        self.session = requests.Session()
        self.booking_context = {}
        
        # Load environment variables from backend/.env
        if backend_env_path is None:
            backend_env_path = Path(__file__).parent.parent / "backend" / ".env"
        
        if backend_env_path.exists():
            load_dotenv(backend_env_path)
        else:
            print(f"⚠️  Warning: .env not found at {backend_env_path}")
        
        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("⚠️  Warning: OPENAI_API_KEY not found in environment")
            self.openai_client = None
        else:
            self.openai_client = OpenAI(api_key=api_key)
        
        # Load system prompt from prompt2.txt
        prompt2_path = Path(__file__).parent / "prompt2.txt"
        self.system_prompt = self._load_system_prompt(prompt2_path)
        
        # Load valid specialties from doctors data
        if doctors_data_path is None:
            doctors_data_path = Path(__file__).parent.parent / "backend" / "data" / "doctors_data.json"
        
        self.valid_specialties = self._load_specialties(doctors_data_path)
    
    # ─────────────────────── INITIALIZATION ─────────────────────────────────
    
    def _load_specialties(self, data_path: str | Path) -> Set[str]:
        """
        Tải danh sách chuyên khoa thực tế từ file dữ liệu bác sĩ.
        
        Args:
            data_path: Đường dẫn tới file doctors_data.json
            
        Returns:
            Set các chuyên khoa hợp lệ
        """
        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                doctors = json.load(f)
            
            specialties = set()
            for doctor in doctors:
                specialty = doctor.get("specialty", "").strip()
                if specialty:
                    specialties.add(specialty)
            
            print(f"✓ Loaded {len(specialties)} specialties from {data_path}")
            return specialties
            
        except FileNotFoundError:
            print(f"⚠️  Warning: doctors_data.json not found at {data_path}")
            print(f"   Using fallback specialties")
            return {
                "Tim mạch", "Nhi", "Ngoại chấn thương chỉnh hình", 
                "Gây mê - điều trị đau", "Nội khoa", "Sản phụ khoa"
            }
        except Exception as e:
            print(f"⚠️  Error loading specialties: {e}")
            return set()
    
    def _load_system_prompt(self, prompt2_path: str | Path) -> str:
        """
        Tải SYSTEM PROMPT từ prompt2.txt.
        
        Args:
            prompt2_path: Đường dẫn tới file prompt2.txt
            
        Returns:
            Nội dung system prompt
        """
        try:
            with open(prompt2_path, 'r', encoding='utf-8') as f:
                prompt = f.read()
            print(f"✓ Loaded system prompt from {prompt2_path}")
            return prompt
        except FileNotFoundError:
            print(f"⚠️  Warning: prompt2.txt not found at {prompt2_path}")
            return "Bạn là trợ lý đặt lịch khám tại Vinmec."
        except Exception as e:
            print(f"⚠️  Error loading prompt2.txt: {e}")
            return "Bạn là trợ lý đặt lịch khám tại Vinmec."
        
    # ─────────────────────────── MAIN FLOW ──────────────────────────────────
    
    def generate_response(self, user_message: str, context: Optional[Dict] = None) -> str:
        """
        Gọi OpenAI API để generate response tự nhiên dựa trên prompt2 và context.
        
        Args:
            user_message: Tin nhắn từ người dùng
            context: Context về booking (specialty, slots, etc.)
            
        Returns:
            Response từ OpenAI hoặc fallback message
        """
        if not self.openai_client:
            print("⚠️  OpenAI client not initialized, using fallback response")
            return "Xin lỗi, hiện tại tôi không thể xử lý yêu cầu của bạn."
        
        # Build context message
        context_msg = ""
        if context:
            if context.get("specialty"):
                context_msg += f"Chuyên khoa được chọn: {context['specialty']}\n"
            if context.get("available_slots"):
                context_msg += f"Khung giờ rảnh: {', '.join(context['available_slots'])}\n"
        
        user_input = f"{context_msg}\nYêu cầu của người dùng: {user_message}" if context_msg else user_message
        
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
            
            response = completion.choices[0].message.content
            return response
            
        except Exception as e:
            print(f"⚠️  OpenAI API error: {e}")
            return "Xin lỗi, có lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại."
    
    def start_booking(self, specialty: str, user_id: str = "guest") -> str:
        """
        Bắt đầu quy trình đặt lịch. Xác nhận chuyên khoa từ Agent 1.
        
        Args:
            specialty: Chuyên khoa (được chuyển từ Agent 1)
            user_id: ID người dùng
            
        Returns:
            Tin nhắn xác nhận chuyên khoa (AI-generated)
        """
        self.booking_context = {
            "specialty": specialty,
            "user_id": user_id,
            "step": "confirm_specialty"
        }
        
        # Generate response using OpenAI
        user_msg = f"Tôi muốn đặt lịch khám chuyên khoa {specialty}. Vui lòng xác nhận và giúp tôi chọn khung giờ."
        return self.generate_response(user_msg, {"specialty": specialty})
    
    def get_available_slots(self, specialty: str) -> Dict[str, Any]:
        """
        Lấy danh sách bác sĩ và khung giờ rảnh theo chuyên khoa.
        
        Args:
            specialty: Chuyên khoa
            
        Returns:
            Dict chứa danh sách bác sĩ và khung giờ
        """
        try:
            # Lấy danh sách bác sĩ theo chuyên khoa
            response = self.session.get(
                f"{self.api_base_url}/doctors",
                params={"specialty": specialty},
                timeout=5
            )
            
            if response.status_code != 200:
                return {"error": "Không thể lấy danh sách bác sĩ"}
            
            doctors = response.json()
            
            if not doctors:
                return {"error": f"Không có bác sĩ chuyên khoa {specialty}"}
            
            # Lấy khung giờ cho từng bác sĩ
            slots_data = {}
            for doctor in doctors:
                doctor_id = doctor.get("id")
                slots_response = self.session.get(
                    f"{self.api_base_url}/doctors/{doctor_id}/slots",
                    timeout=5
                )
                
                if slots_response.status_code == 200:
                    slots_info = slots_response.json()
                    slots_data[doctor_id] = {
                        "name": doctor.get("name"),
                        "title": doctor.get("title", ""),
                        "clinic": doctor.get("clinic", ""),
                        "slots": slots_info.get("slots", [])
                    }
            
            return {
                "specialty": specialty,
                "doctors": slots_data,
                "count": len(slots_data)
            }
            
        except requests.exceptions.RequestException as e:
            return {"error": f"Lỗi kết nối API: {str(e)}"}
    
    def suggest_appointment_options(self, specialty: str) -> str:
        """
        Đưa ra danh sách khung giờ rảnh (Sáng/Chiều) cho người dùng chọn lựa.
        
        Args:
            specialty: Chuyên khoa
            
        Returns:
            Tin nhắn với danh sách khung giờ được đề xuất (AI-generated)
        """
        slots_data = self.get_available_slots(specialty)
        
        if "error" in slots_data:
            return f"❌ {slots_data['error']}"
        
        if slots_data["count"] == 0:
            return self.generate_response(
                f"Không có lịch khám nào cho chuyên khoa {specialty}. Vui lòng đề xuất cách khách hàng liên hệ tổng đài.",
                {"specialty": specialty}
            )
        
        # Organize suggestions
        morning_slots = []
        afternoon_slots = []
        slot_list = []
        
        for doctor_id, doctor_info in slots_data["doctors"].items():
            slots = doctor_info["slots"]
            doctor_name = doctor_info["name"]
            
            for slot in slots:
                hour = int(slot.split(":")[0])
                slot_obj = {
                    "doctor_id": doctor_id,
                    "doctor_name": doctor_name,
                    "slot": slot
                }
                slot_list.append(slot_obj)
                
                if hour < 12:
                    morning_slots.append({**slot_obj, "type": "Sáng"})
                else:
                    afternoon_slots.append({**slot_obj, "type": "Chiều"})
        
        # Store for later use
        self.booking_context["morning_slots"] = morning_slots
        self.booking_context["afternoon_slots"] = afternoon_slots
        self.booking_context["step"] = "select_slot"
        
        # Format available slots for context
        slots_str = ""
        if morning_slots:
            slots_str += "Sáng: " + ", ".join([f"{s['slot']} ({s['doctor_name']})" for s in morning_slots[:3]])
        if afternoon_slots:
            if slots_str:
                slots_str += "; "
            slots_str += "Chiều: " + ", ".join([f"{s['slot']} ({s['doctor_name']})" for s in afternoon_slots[:3]])
        
        # Generate response with AI
        user_msg = f"Cần giúp khách hàng chọn khung giờ khám chuyên khoa {specialty}. Đưa ra 2 gợi ý (Sáng/Chiều)."
        context = {
            "specialty": specialty,
            "available_slots": [f"{s['slot']} ({s['doctor_name']})" for s in slot_list[:6]]
        }
        
        return self.generate_response(user_msg, context)
    
    def create_booking(self, doctor_id: str, slot: str, booking_date: str) -> str:
        """
        Tạo lịch hẹn sau khi người dùng xác nhận.
        
        Args:
            doctor_id: ID bác sĩ
            slot: Khung giờ (VD: "09:00")
            booking_date: Ngày hẹn (VD: "15/04/2026")
            
        Returns:
            Tin nhắn xác nhận hoặc lỗi
        """
        try:
            appointment_data = {
                "doctorId": doctor_id,
                "slot": slot,
                "date": booking_date,
                "userId": self.booking_context.get("user_id", "guest")
            }
            
            response = self.session.post(
                f"{self.api_base_url}/appointments",
                json=appointment_data,
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                appointment = response.json()
                return self._format_confirmation(appointment)
            else:
                error_msg = response.json().get("detail", "Không xác định")
                return f"❌ Lỗi đặt lịch: {error_msg}"
                
        except requests.exceptions.RequestException as e:
            return f"❌ Lỗi kết nối: {str(e)}"
    
    def final_confirmation(self, doctor_id: str, doctor_name: str, 
                          specialty: str, slot: str, booking_date: str) -> str:
        """
        Xác nhận cuối cùng trước khi tạo lịch hẹn.
        
        Args:
            doctor_id: ID bác sĩ
            doctor_name: Tên bác sĩ
            specialty: Chuyên khoa
            slot: Khung giờ
            booking_date: Ngày hẹn
            
        Returns:
            Tin nhắn xác nhận (AI-generated)
        """
        self.booking_context.update({
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "slot": slot,
            "booking_date": booking_date,
            "step": "final_confirm"
        })
        
        # Generate confirmation message with AI
        user_msg = f"Xác nhận lịch khám: Chuyên khoa {specialty}, BS {doctor_name}, {slot}, ngày {booking_date}. Yêu cầu xác nhận là chính xác hay cần sửa."
        context = {
            "specialty": specialty,
            "doctor_name": doctor_name,
            "slot": slot,
            "booking_date": booking_date
        }
        
        return self.generate_response(user_msg, context)
    
    # ────────────────────────── HELPER METHODS ──────────────────────────────
    
    def _format_confirmation(self, appointment: Dict) -> str:
        """Định dạng tin nhắn xác nhận lịch hẹn (AI-generated)."""
        # Generate success message with AI
        user_msg = f"Đặt lịch thành công. BS {appointment.get('doctor')} chuyên khoa {appointment.get('specialty')}, {appointment.get('slot')} ngày {appointment.get('date')}. Thành công!"
        return self.generate_response(user_msg, {"appointment": appointment})
    
    def handle_escalation(self, reason: str) -> str:
        """
        Xử lý khi cần chuyển sang nhân viên tư vấn hoặc tổng đài viên.
        
        Args:
            reason: Lý do escalate
            
        Returns:
            Tin nhắn thông báo escalation
        """
        escalation_msg = (
            f"Xin lỗi, tôi không thể xử lý yêu cầu này.\n\n"
            f"Lý do: {reason}\n\n"
            f"Tôi sẽ chuyển bạn tới nhân viên tư vấn hoặc tổng đài viên Vinmec.\n"
            f"Vui lòng chờ một lát... ⏳"
        )
        return escalation_msg
    
    def validate_specialty(self, specialty: str) -> bool:
        """
        Kiểm tra xem chuyên khoa có trong danh sách hợp lệ không (từ dữ liệu bác sĩ).
        Hỗ trợ tìm kiếm không phân biệt hoa/thường.
        
        Args:
            specialty: Tên chuyên khoa cần kiểm tra
            
        Returns:
            True nếu chuyên khoa hợp lệ, False nếu không
        """
        if not specialty or not self.valid_specialties:
            return False
        
        # Exact match
        if specialty in self.valid_specialties:
            return True
        
        # Case-insensitive fuzzy match
        specialty_lower = specialty.lower().strip()
        for valid_spec in self.valid_specialties:
            if specialty_lower == valid_spec.lower():
                return True
            # Partial match for multi-word specialties
            if specialty_lower in valid_spec.lower() or valid_spec.lower() in specialty_lower:
                return True
        
        return False


# ────────────────────────────────────────────────────────────────────────────
# USAGE EXAMPLE
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Initialize agent
    # Sẽ tự động load:
    # - OPENAI_API_KEY từ backend/.env
    # - SYSTEM_PROMPT từ agent/prompt2.txt
    # - Valid specialties từ backend/data/doctors_data.json
    agent = VinmecBookingAgent()
    
    if agent.openai_client is None:
        print("❌ ERROR: OPENAI_API_KEY not found in backend/.env")
        print("   Ensure backend/.env has OPENAI_API_KEY=sk-...")
        exit(1)
    
    print(f"Valid specialties loaded: {agent.valid_specialties}\n")
    print("="*60)
    print("=== VINMEC BOOKING AGENT (WITH AI) ===\n")
    
    # Step 1: Start booking
    specialty = "Tim mạch"
    print(f"📋 Step 1: Starting booking for '{specialty}'")
    print(f"✓ Validating specialty: Valid={agent.validate_specialty(specialty)}\n")
    
    greeting = agent.start_booking(specialty)
    print("🤖 AI Response:")
    print(greeting)
    print("\n" + "─"*60 + "\n")
    
    # Step 2: Get available slots
    print(f"📋 Step 2: Fetching available slots for '{specialty}'")
    suggestions = agent.suggest_appointment_options(specialty)
    print("🤖 AI Response:")
    print(suggestions)
    print("\n" + "─"*60 + "\n")
    
    # Step 3: Final confirmation
    print(f"📋 Step 3: Final confirmation before booking")
    doctor_id = "doc-0001"
    doctor_name = "PGS.TS Đỗ Tất Cường"
    slot = "09:00"
    booking_date = "15/04/2026"
    
    confirmation = agent.final_confirmation(doctor_id, doctor_name, specialty, slot, booking_date)
    print("🤖 AI Response:")
    print(confirmation)
