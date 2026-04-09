const API_BASE = "http://localhost:8000/api";

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  messages: [],
  history: [],          // lịch sử gửi lên OpenAI [{role, content}]
  currentStep: null,    // bước hiện tại trong flow
  suggestedDoctors: [],
  selectedDoctorIndex: 0,
  selectedSlot: null,
  appointments: [],
  chatSessions: [],
  activeSessionId: null,
  latestSymptom: "Chưa có mô tả triệu chứng.",
};

const el = {
  chatFeed: document.getElementById("chat-feed"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  doctorList: document.getElementById("doctor-list"),
  doctorDetail: document.getElementById("doctor-detail"),
  doctorIndex: document.getElementById("doctor-index"),
  doctorTotal: document.getElementById("doctor-total"),
  prevDoctor: document.getElementById("prev-doctor"),
  nextDoctor: document.getElementById("next-doctor"),
  appointmentList: document.getElementById("appointment-list"),
  appointmentCount: document.getElementById("appointment-count"),
  latestSymptomText: document.getElementById("latest-symptom-text"),
  consultHistory: document.getElementById("consult-history"),
};

// ── API helpers ───────────────────────────────────────────────────────────────

async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} thất bại: ${res.status}`);
  return res.json();
}

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} thất bại: ${res.status}`);
  return res.json();
}

async function apiPatch(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${path} thất bại: ${res.status}`);
  return res.json();
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function currentDoctor() {
  return state.suggestedDoctors[state.selectedDoctorIndex];
}

function cloneMessages(messages) {
  return messages.map((m) => ({ ...m }));
}

// ── Session sync ──────────────────────────────────────────────────────────────

async function syncActiveSession(overrides = {}) {
  if (!state.activeSessionId) return;
  const local = state.chatSessions.find((s) => s.id === state.activeSessionId);
  if (local) {
    local.messages = cloneMessages(state.messages);
    if (overrides.symptom) local.symptom = overrides.symptom;
    if (overrides.summary) local.summary = overrides.summary;
    if (overrides.time)    local.time    = overrides.time;
  }
  try {
    await apiPatch(`/sessions/${state.activeSessionId}`, {
      messages: state.messages,
      ...overrides,
    });
  } catch { /* non-critical */ }
  renderConsultHistory();
}

async function startNewSession(symptomText) {
  try {
    const session = await apiPost("/sessions", { symptom: symptomText });
    state.chatSessions.push(session);
    state.activeSessionId = session.id;
  } catch {
    const session = {
      id: `local-${Date.now()}`,
      symptom: symptomText,
      summary: "Đang tư vấn.",
      time: "Vừa xong",
      messages: [],
    };
    state.chatSessions.push(session);
    state.activeSessionId = session.id;
  }
  renderConsultHistory();
}

async function loadSessions() {
  try {
    state.chatSessions = await apiGet("/sessions?userId=guest");
    renderConsultHistory();
  } catch { /* skip */ }
}

async function loadAppointments() {
  try {
    state.appointments = await apiGet("/appointments?userId=guest");
    renderAppointments();
  } catch { /* skip */ }
}

async function loadDefaultDoctors() {
  try {
    const doctors = await apiGet("/doctors");
    if (state.suggestedDoctors.length === 0 && doctors.length > 0) {
      state.suggestedDoctors = doctors.slice(0, 3);
      state.selectedDoctorIndex = 0;
      state.selectedSlot = state.suggestedDoctors[0]?.slots[0] ?? null;
      renderDoctorList();
      renderDoctorDetail();
    }
  } catch { /* skip */ }
}

// ── Render ────────────────────────────────────────────────────────────────────

function pushMessage(sender, text, step = null) {
  state.messages.push({
    id: `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    sender,
    text,
    step,
  });
  syncActiveSession();
  renderMessages();
}

function renderMessages() {
  el.chatFeed.innerHTML = "";

  state.messages.forEach((msg) => {
    const bubble = document.createElement("article");
    bubble.className = `chat-bubble ${msg.sender}`;

    const lines = msg.text.split("\n");
    bubble.innerHTML = lines.map((line) => `<p>${line}</p>`).join("");

    // Render action buttons theo step
    if (msg.sender === "bot" && msg.step) {
      const actions = document.createElement("div");
      actions.className = "chat-actions";

      if (msg.step === "analyze") {
        // Bước 1: xác nhận chuyên khoa hay không
        actions.appendChild(_makeBtn("Xác nhận khoa này", "confirm-btn", () => sendQuickReply("Tôi đồng ý với chuyên khoa này")));
        actions.appendChild(_makeBtn("Tư vấn nhân viên", "other-btn", () => sendQuickReply("Tôi muốn tư vấn với nhân viên")));

      } else if (msg.step === "ask_time") {
        // Bước 2: chọn buổi → lọc slot trực tiếp, không qua OpenAI
        actions.appendChild(_makeBtn("Buổi sáng", "confirm-btn", () => pickSlotBySession("morning")));
        actions.appendChild(_makeBtn("Buổi chiều", "other-btn",  () => pickSlotBySession("afternoon")));

      } else if (msg.step === "suggest_slot") {
        // Bước 3: xác nhận lịch hẹn cụ thể
        actions.appendChild(_makeBtn("Xác nhận lịch", "confirm-btn", confirmAppointment));
        actions.appendChild(_makeBtn("Chọn giờ khác", "other-btn", pickNextSlot));

      } else if (msg.step === "consult_staff") {
        // Kết nối nhân viên
        actions.appendChild(_makeBtn("Gọi nhân viên tư vấn", "confirm-btn", () => {
          pushMessage("bot", "Đang kết nối bạn với nhân viên tư vấn. Vui lòng chờ trong giây lát...");
        }));
      }

      bubble.appendChild(actions);
    }

    el.chatFeed.appendChild(bubble);
  });

  el.chatFeed.scrollTop = el.chatFeed.scrollHeight;
}

function _makeBtn(label, className, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = className;
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

function renderAppointments() {
  el.appointmentList.innerHTML = "";
  el.appointmentCount.textContent = `${state.appointments.length} lịch`;

  if (state.appointments.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Bạn chưa xác nhận lịch nào.";
    el.appointmentList.appendChild(empty);
    return;
  }

  state.appointments.slice().reverse().forEach((item) => {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${item.date} - ${item.slot}</strong><span>${item.doctor} | ${item.specialty}</span>`;
    el.appointmentList.appendChild(li);
  });
}

function renderConsultHistory() {
  el.consultHistory.innerHTML = "";
  state.chatSessions.slice().reverse().forEach((item) => {
    const li = document.createElement("li");
    li.className = `consult-session ${item.id === state.activeSessionId ? "active" : ""}`;
    li.innerHTML = `<strong>${item.symptom}</strong><span>${item.summary} (${item.time})</span>`;
    li.addEventListener("click", () => {
      state.activeSessionId = item.id;
      state.messages = cloneMessages(item.messages || []);
      state.history = [];
      state.latestSymptom = item.symptom;

      // Restore doctors của session này nếu có
      if (item.doctors?.length) {
        state.suggestedDoctors = item.doctors;
        state.selectedDoctorIndex = 0;
        state.selectedSlot = item.doctors[0]?.slots[0] ?? null;
        renderDoctorList();
        renderDoctorDetail();
      }

      renderLatestSymptom();
      renderMessages();
      renderConsultHistory();
    });
    el.consultHistory.appendChild(li);
  });
}

function renderLatestSymptom() {
  el.latestSymptomText.textContent = state.latestSymptom;
}

function renderDoctorList() {
  el.doctorList.innerHTML = "";
  el.doctorTotal.textContent = state.suggestedDoctors.length;
  el.doctorIndex.textContent = state.selectedDoctorIndex + 1;

  state.suggestedDoctors.forEach((doc, index) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `doctor-chip ${index === state.selectedDoctorIndex ? "active" : ""}`;
    chip.textContent = doc.name;
    chip.addEventListener("click", () => {
      state.selectedDoctorIndex = index;
      if (!doc.slots.includes(state.selectedSlot)) state.selectedSlot = doc.slots[0];
      renderDoctorList();
      renderDoctorDetail();
    });
    const li = document.createElement("li");
    li.appendChild(chip);
    el.doctorList.appendChild(li);
  });
}

function renderDoctorDetail() {
  if (!currentDoctor()) return;
  const doc = currentDoctor();

  el.doctorDetail.innerHTML = `
    <div class="doctor-hero">
      <img src="${doc.image}" alt="Ảnh bác sĩ ${doc.name}" />
      <div>
        <h3>${doc.name}</h3>
        <p>${doc.specialty}</p>
        <p>${doc.title || ""}</p>
      </div>
    </div>
    <div class="info-grid">
      <div><p>Phòng khám</p><strong>${doc.clinic}</strong></div>
    </div>
    <div class="slot-wrap">
      <p>Khung giờ trống</p>
      <div id="slot-row" class="slot-row"></div>
    </div>
    <button id="doctors-action" type="button">Chọn bác sĩ này</button>
  `;

  const slotRow = document.getElementById("slot-row");
  doc.slots.forEach((slot) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `slot-btn ${slot === state.selectedSlot ? "active" : ""}`;
    btn.textContent = slot;
    btn.addEventListener("click", () => { state.selectedSlot = slot; renderDoctorDetail(); });
    slotRow.appendChild(btn);
  });

  document.getElementById("doctors-action").addEventListener("click", () => {
    // Không qua OpenAI — dùng slot thực tế đang chọn trong panel
    pushMessage("user", `Tôi chọn bác sĩ ${doc.name}, giờ ${state.selectedSlot}`);
    state.currentStep = "suggest_slot";
    pushMessage(
      "bot",
      `Bạn đã chọn bác sĩ **${doc.name}** (${doc.specialty})\nKhung giờ: **${state.selectedSlot}**\nPhòng khám: ${doc.clinic}\n\nBạn có muốn xác nhận lịch hẹn này không?`,
      "suggest_slot"
    );
  });
}

// ── Actions ───────────────────────────────────────────────────────────────────

// Lọc slot theo buổi sáng/chiều, chuyển thẳng sang suggest_slot
function pickSlotBySession(session) {
  const doc = currentDoctor();
  if (!doc) return;

  const slots = session === "morning"
    ? doc.slots.filter((s) => parseInt(s) < 12)
    : doc.slots.filter((s) => parseInt(s) >= 12);

  const label = session === "morning" ? "buổi sáng" : "buổi chiều";

  if (slots.length === 0) {
    pushMessage("bot", `Bác sĩ ${doc.name} không có khung giờ ${label}. Vui lòng chọn buổi khác.`, "ask_time");
    return;
  }

  state.selectedSlot = slots[0];
  renderDoctorDetail();
  state.currentStep = "suggest_slot";
  pushMessage(
    "bot",
    `Khung giờ ${label} còn trống: ${slots.join(", ")}.\nMình gợi ý bạn khám lúc **${slots[0]}** với bác sĩ ${doc.name}.\nBạn có muốn xác nhận không?`,
    "suggest_slot"
  );
}

// Xoay sang slot tiếp theo trong panel (không qua OpenAI)
function pickNextSlot() {
  const doc = currentDoctor();
  if (!doc) return;
  const idx = doc.slots.indexOf(state.selectedSlot);
  state.selectedSlot = doc.slots[(idx + 1) % doc.slots.length];
  renderDoctorDetail();
  pushMessage(
    "bot",
    `Đã chuyển sang khung giờ **${state.selectedSlot}** với ${doc.name}.\nBạn có muốn xác nhận lịch này không?`,
    "suggest_slot"
  );
}

// Gửi tin nhắn nhanh (từ button) mà không cần user gõ
async function sendQuickReply(text) {
  pushMessage("user", text);
  await callChatAPI(text);
}

async function confirmAppointment() {
  const doc = currentDoctor();
  if (!doc || !state.selectedSlot) return;

  const now = new Date();
  const dateLabel = now.toLocaleDateString("vi-VN", {
    day: "2-digit", month: "2-digit", year: "numeric",
  });

  try {
    const appt = await apiPost("/appointments", {
      doctorId: doc.id,
      slot: state.selectedSlot,
      date: dateLabel,
      userId: "guest",
    });
    state.appointments.push(appt);
  } catch {
    state.appointments.push({
      doctor: doc.name,
      specialty: doc.specialty,
      slot: state.selectedSlot,
      date: dateLabel,
    });
  }

  renderAppointments();

  // Không qua OpenAI — push message thành công trực tiếp
  state.currentStep = "confirmed";
  pushMessage(
    "bot",
    `Đã xác nhận lịch thành công! 🎉\nBác sĩ: ${doc.name}\nChuyên khoa: ${doc.specialty}\nThời gian: ${dateLabel} lúc ${state.selectedSlot}\nPhòng khám: ${doc.clinic}`,
    "confirmed"
  );

  syncActiveSession({
    summary: `Đã đặt với ${doc.name} lúc ${state.selectedSlot}`,
    time: "Vừa xong",
  });
}

// ── Core chat call ────────────────────────────────────────────────────────────

async function callChatAPI(userText) {
  try {
    const doc = currentDoctor();
    const doctorContext = doc
      ? `Bác sĩ: ${doc.name} | Chuyên khoa: ${doc.specialty} | Phòng khám: ${doc.clinic} | Khung giờ có sẵn: ${doc.slots.join(", ")}`
      : "";

    const result = await apiPost("/chat", {
      message: userText,
      history: state.history,
      doctor_context: doctorContext,
    });

    // Cập nhật history cho lượt tiếp
    state.history.push({ role: "user", content: userText });
    state.history.push({ role: "assistant", content: result.message });

    state.currentStep = result.step;

    // Nếu bước analyze → cập nhật danh sách bác sĩ và lưu vào session
    if (result.step === "analyze" && result.doctor_suggestion?.length) {
      state.suggestedDoctors = result.doctor_suggestion;
      state.selectedDoctorIndex = 0;
      state.selectedSlot = result.doctor_suggestion[0]?.slots[0] ?? null;
      renderDoctorList();
      renderDoctorDetail();

      // Lưu doctors vào session local để restore khi click lịch sử
      const local = state.chatSessions.find((s) => s.id === state.activeSessionId);
      if (local) local.doctors = result.doctor_suggestion;
    }

    pushMessage("bot", result.message, result.step);

    syncActiveSession({
      symptom: state.latestSymptom,
      summary: _stepSummary(result.step),
      time: "Vừa xong",
    });
  } catch {
    pushMessage("bot", "Không thể kết nối đến server. Vui lòng thử lại sau.");
  }
}

function _stepSummary(step) {
  const map = {
    analyze: "Đã phân tích triệu chứng.",
    ask_time: "Đang hỏi thời gian khám.",
    suggest_slot: "Đã đề xuất lịch hẹn.",
    confirmed: "Đã đặt lịch thành công.",
    consult_staff: "Chuyển sang nhân viên tư vấn.",
  };
  return map[step] || "Đang tư vấn.";
}

// ── Event handling ────────────────────────────────────────────────────────────

async function handleSubmit(event) {
  event.preventDefault();
  const inputText = el.chatInput.value.trim();
  if (!inputText) return;

  state.latestSymptom = inputText;
  renderLatestSymptom();

  // Chỉ tạo session mới khi chưa có session nào đang active
  if (!state.activeSessionId) {
    state.messages = [];
    state.history = [];
    state.currentStep = null;
    renderMessages();
    await startNewSession(inputText);
  }

  pushMessage("user", inputText);
  el.chatInput.value = "";
  await callChatAPI(inputText);
}

function bindEvents() {
  el.chatForm.addEventListener("submit", handleSubmit);

  document.getElementById("new-chat-btn").addEventListener("click", () => {
    state.messages = [];
    state.history = [];
    state.currentStep = null;
    state.activeSessionId = null;
    renderMessages();
    renderConsultHistory();
    pushMessage(
      "bot",
      "Xin chào! Bạn hãy mô tả triệu chứng để mình tìm chuyên khoa và bác sĩ phù hợp nhé."
    );
  });

  el.prevDoctor.addEventListener("click", () => {
    const total = state.suggestedDoctors.length;
    if (!total) return;
    state.selectedDoctorIndex = (state.selectedDoctorIndex - 1 + total) % total;
    if (!currentDoctor().slots.includes(state.selectedSlot)) state.selectedSlot = currentDoctor().slots[0];
    renderDoctorList();
    renderDoctorDetail();
  });

  el.nextDoctor.addEventListener("click", () => {
    const total = state.suggestedDoctors.length;
    if (!total) return;
    state.selectedDoctorIndex = (state.selectedDoctorIndex + 1) % total;
    if (!currentDoctor().slots.includes(state.selectedSlot)) state.selectedSlot = currentDoctor().slots[0];
    renderDoctorList();
    renderDoctorDetail();
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  pushMessage(
    "bot",
    "Xin chào! Mình là trợ lý đặt lịch khám của MediFlow.\nBạn hãy mô tả triệu chứng để mình tìm chuyên khoa và bác sĩ phù hợp nhé."
  );

  renderLatestSymptom();
  renderAppointments();
  bindEvents();

  await Promise.all([loadSessions(), loadAppointments(), loadDefaultDoctors()]);
}

init();
