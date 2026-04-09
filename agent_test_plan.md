# Test & Fix Plan: Handling Greetings in Agent Service

## 1. Problem Statement
When a user inputs a greeting (e.g., "hi", "hello"), the system incorrectly returns an unrelated medical specialty and inaccurate doctor suggestions. This happens because the system forces a fallback to specialty parsing and doctor retrieval even when the user hasn't provided any symptoms.

## 2. Root Cause Analysis
In `backend/app/services/agent_service.py`, the method `_infer_intent` only returns `symptom` or `booking`. Greetings are lumped into `symptom`. Subsequently, `_extract_specialty_from_text` falls back to `"Nội tổng quát"` if no specialty is found in the LLM's response, which mistakenly triggers `_build_suggestions` and returns doctors.

## 3. Implementation Plan (For the Agent)

### A. Update Intent Classification
Modify `AgentService._infer_intent` to support a new intent type: `"greeting"`.
- Update the prompt to classify into three categories: `"symptom"`, `"booking"`, or `"greeting"`.

### B. Update Chat Logic (`AgentService.chat`)
Implement a conditional branch for the `"greeting"` intent.
- If `intent == "greeting"`:
  - Do not call `self.agent1.handle_request()` if not necessary.
  - Return a static greeting message: `"Xin chào! Bạn hãy mô tả triệu chứng để mình tìm chuyên khoa và bác sĩ phù hợp nhé."`
  - Ensure `suggestions` and `doctor_suggestion` are empty arrays `[]`.
  - Set the step to `"greeting"` or `"ask_symptom"`.

### C. Prevent Unnecessary Fallbacks
Review `_extract_specialty_from_text`. If the system must pass through the `symptom` logic for a short input without symptoms, detect the absence of specialties and return `None` (or empty string) instead of defaulting to `"Nội tổng quát"` for non-symptom-related small talk.

## 4. Test Cases

| Test Case | User Input | Expected Action | Expected Output State |
| :--- | :--- | :--- | :--- |
| **TC-01: Simple Greeting** | `"hi"` / `"hello"` | Agent recognizes greeting without extracting specialty. | message: "Xin chào...", doctor_suggestion: `[]` |
| **TC-02: Small Talk / Invalid** | `"bạn tên gì?"` | Agent asks user to provide medical symptoms. | message: Prompts for symptoms, doctor_suggestion: `[]` |
| **TC-03: Valid Symptom** | `"tôi bị đau đầu chóng mặt"` | Agent triggers standard AI diagnosis. | message: Diagnosis text, doctor_suggestion: `[...]` (contains Neurologists) |

## 5. Verification
1. Run backend server.
2. Use the frontend UI to send `"hi"`.
3. Verify that the response does NOT contain any doctor suggestions and asks for symptoms.

## 6. Prompt cho Cursor / Agent (Copy & Paste)
```text
@agent_service.py @doctors_data.json
Fix the doctor suggestion bug: When a user inputs a symptom like "tôi bị đau bụng", the system currently fails to suggest any doctors (UI shows "Chưa có bác sĩ được đề xuất"). 
1. Ensure the LLM correctly diagnoses the symptom and returns a valid specialty (e.g., "Tiêu hóa" or "Nội Tiêu hóa").
2. Ensure `_extract_specialty_from_text` properly extracts this specialty.
3. Ensure `_build_suggestions` returns a non-empty list of matching doctors from `doctors_data.json`.
4. At the same time, implement the logic from the plan above to prevent greetings ("hi") from auto-triggering doctor predictions.
```

## 7. Cập nhật Văn phong & Logic Chọn Giờ (Copy & Paste cho Cursor)
```text
@agent_service.py @agent1.py @agent2.py @prompt1.txt (or equivalents)
Please update the system to fulfill these two new requirements:

1. Update the AI System Prompt / Response logic. When the user inputs symptoms, the AI MUST respond exactly following this polite template structure (fill in the symptom and specialty variables appropriately):
"Dạ, Vinmec xin chào Anh/Chị. Rất vui được hỗ trợ Anh/Chị trong việc chăm sóc sức khỏe. Anh/Chị đang gặp phải triệu chứng [TÊN TRIỆU CHỨNG], có thể liên quan đến một số vấn đề như chướng bụng, đầy hơi hoặc các vấn đề tiêu hóa khác.

Vinmec kính mời Anh/Chị đến thăm khám cùng các chuyên gia tại Khoa [TÊN CHUYÊN KHOA] để được kiểm tra kỹ lưỡng nhất ạ.

Để Anh/Chị không phải chờ đợi lâu khi đến viện, Anh/Chị dự định thăm khám vào ngày nào và khung giờ nào thuận tiện nhất ạ? Em sẽ hỗ trợ kiểm tra lịch bác sĩ và đặt hẹn cho Anh/Chị ngay ạ."

2. Fix the manual time-slot selection logic (in booking phase). If the user inputs a specific time text (e.g., "15h30" or "15:30") instead of clicking buttons:
- Extract the time and check it against the selected doctor's available slots.
- If the slot is available (or has a match like 15:30): Immediately confirm the appointment for that slot.
- If the slot is NOT available: Reply that the slot is unavailable and ask the user to pick another slot from the available ones.
```

## 8. Cập nhật Template Tư Vấn & Logic Hỏi Lại (Copy & Paste cho Cursor)
```text
@agent_service.py @agent1.py @prompt1.txt (or equivalents)
Please update the AI diagnostic logic and response template to meet these requirements:

1. Update the AI Response Template to EXACTLY this format (remove the previous date/time booking question from this intent step):
"Dạ, Vinmec xin chào Anh/Chị. Anh/Chị đang gặp phải triệu chứng [TÊN TRIỆU CHỨNG], có thể liên quan đến một số vấn đề như [CÁC VẤN ĐỀ LIÊN QUAN].

Vinmec kính mời Anh/Chị đến thăm khám cùng các chuyên gia tại Khoa [TÊN KHOA] để được kiểm tra kỹ lưỡng nhất ạ."

2. Implement a 1-Time Clarification Logic for Vague Symptoms:
- If the user provides a very short or vague symptom initially (e.g., just "đau đầu"), the AI should ask for more details to clarify EXACTLY ONCE.
- If the user provides more details in their next message, diagnose and suggest the specialty normally.
- If the user repeats the vague symptom again without adding details (e.g., says "đau đầu" again), DO NOT ask again. Proceed immediately to suggest the most likely specialty (e.g., "Nội Thần kinh") using the template above.
- If the initial symptom is already detailed and clear, skip clarification and suggest the specialty immediately.
```

## 9. Logic Đổi Bác Sĩ & Không Trùng Lặp (Copy & Paste cho Cursor)
```text
@agent_service.py @app.js
Please fix the system's "request other doctors" logic:

When the user asks "còn bác sĩ nào khác không" or "đổi bác sĩ":
1. The backend MUST return exactly 3 doctors for the current specialty. (Currently it sometimes only suggests 1).
2. Fix the duplication bug: Ensure the suggested doctors DO NOT REPEAT.
3. Update `_build_suggestions` (using session history, tracked IDs, or offsets) to filter out both duplicates within the new array of 3, AND doctors that were already shown in the previous turn. Every "đổi bác sĩ" request must yield 3 entirely NEW and UNIQUE doctors.
```
