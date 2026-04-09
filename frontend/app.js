const API_BASE = "http://localhost:8000/api";

const state = {
  messages: [],
  history: [],
  currentStep: "",
  suggestedDoctors: [],
  selectedDoctorIndex: 0,
  selectedSlot: null,
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
  newChatBtn: document.getElementById("new-chat-btn"),
};

async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    throw new Error(`POST ${path} thất bại: ${res.status}`);
  }

  return res.json();
}

function currentDoctor() {
  return state.suggestedDoctors[state.selectedDoctorIndex];
}

function pushMessage(sender, text, step = "") {
  state.messages.push({
    id: `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    sender,
    text,
    step,
  });
  renderMessages();
}

function makeBtn(label, className, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = className;
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

function renderMessages() {
  el.chatFeed.innerHTML = "";

  state.messages.forEach((msg) => {
    const bubble = document.createElement("article");
    bubble.className = `chat-bubble ${msg.sender}`;

    const lines = msg.text.split("\n");
    bubble.innerHTML = lines.map((line) => `<p>${line}</p>`).join("");

    if (msg.sender === "bot" && msg.step) {
      const actions = document.createElement("div");
      actions.className = "chat-actions";

      if (msg.step === "analyze") {
        actions.appendChild(makeBtn("Xác nhận khoa này", "confirm-btn", () => sendQuickReply("Tôi đồng ý với chuyên khoa này")));
        actions.appendChild(makeBtn("Tư vấn nhân viên", "other-btn", () => sendQuickReply("Tôi muốn tư vấn với nhân viên")));
      } else if (msg.step === "ask_time") {
        actions.appendChild(makeBtn("Buổi sáng", "confirm-btn", () => pickSlotBySession("morning")));
        actions.appendChild(makeBtn("Buổi chiều", "other-btn", () => pickSlotBySession("afternoon")));
      } else if (msg.step === "suggest_slot") {
        actions.appendChild(makeBtn("Xác nhận lịch", "confirm-btn", confirmAppointment));
        actions.appendChild(makeBtn("Chọn giờ khác", "other-btn", pickNextSlot));
      } else if (msg.step === "consult_staff") {
        actions.appendChild(makeBtn("Gọi nhân viên tư vấn", "confirm-btn", () => {
          pushMessage("bot", "Đang kết nối bạn với nhân viên tư vấn. Vui lòng chờ trong giây lát...");
        }));
      }

      bubble.appendChild(actions);
    }

    el.chatFeed.appendChild(bubble);
  });

  el.chatFeed.scrollTop = el.chatFeed.scrollHeight;
}

function renderDoctorList() {
  el.doctorList.innerHTML = "";
  el.doctorTotal.textContent = String(state.suggestedDoctors.length || 1);
  el.doctorIndex.textContent = String((state.selectedDoctorIndex || 0) + 1);

  state.suggestedDoctors.forEach((doc, index) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `doctor-chip ${index === state.selectedDoctorIndex ? "active" : ""}`;
    chip.textContent = doc.name || doc.doctor_name || "Bác sĩ";

    chip.addEventListener("click", () => {
      state.selectedDoctorIndex = index;
      const slots = doc.slots || [];
      if (!slots.includes(state.selectedSlot)) {
        state.selectedSlot = slots[0] || null;
      }
      renderDoctorList();
      renderDoctorDetail();
    });

    const li = document.createElement("li");
    li.appendChild(chip);
    el.doctorList.appendChild(li);
  });
}

function renderDoctorDetail() {
  const doc = currentDoctor();
  if (!doc) {
    el.doctorDetail.innerHTML = '<p class="empty-state">Chưa có bác sĩ được đề xuất.</p>';
    return;
  }

  const name = doc.name || doc.doctor_name || "Bác sĩ";
  const image = doc.image || doc.profile_image_url || doc.doctor_url || "";
  const specialty = doc.specialty || "";
  const clinic = doc.clinic || doc.workplace || "";
  const id = doc.id || "";
  const rating = typeof doc.rating === "number" ? doc.rating.toFixed(1) : (doc.rating || "");

  el.doctorDetail.innerHTML = `
    <div class="doctor-hero">
      <img src="${image}" alt="Ảnh bác sĩ ${name}" />
      <div>
        <h3>${name}</h3>
        <p>${specialty}</p>
        <p>${doc.title || ""}</p>
      </div>
    </div>
    <div class="info-grid">
      <div><p>Học hàm/Học vị</p><strong>${doc.title || ""}</strong></div>
      <div><p>Chuyên khoa</p><strong>${specialty}</strong></div>
      <div class="info-grid-full"><p>Phòng khám</p><strong>${clinic}</strong></div>
      <div><p>Đánh giá</p><strong>${rating}</strong></div>
      <div><p>Mã bác sĩ</p><strong>${id}</strong></div>
    </div>
  `;
}

function pickSlotBySession(session) {
  const doc = currentDoctor();
  if (!doc) {
    return;
  }

  const slots = doc.slots || [];
  const filteredSlots = session === "morning"
    ? slots.filter((s) => parseInt(s, 10) < 12)
    : slots.filter((s) => parseInt(s, 10) >= 12);

  const label = session === "morning" ? "buổi sáng" : "buổi chiều";

  if (filteredSlots.length === 0) {
    pushMessage("bot", `Bác sĩ ${doc.name || doc.doctor_name} không có khung giờ ${label}. Vui lòng chọn buổi khác.`, "ask_time");
    return;
  }

  state.selectedSlot = filteredSlots[0];
  renderDoctorDetail();
  state.currentStep = "suggest_slot";

  pushMessage(
    "bot",
    `Khung giờ ${label} còn trống: ${filteredSlots.join(", ")}.\nMình gợi ý bạn khám lúc **${filteredSlots[0]}** với bác sĩ ${doc.name || doc.doctor_name}.\nBạn có muốn xác nhận không?`,
    "suggest_slot"
  );
}

function pickNextSlot() {
  const doc = currentDoctor();
  if (!doc) {
    return;
  }

  const slots = doc.slots || [];
  if (slots.length === 0) {
    return;
  }

  const idx = Math.max(slots.indexOf(state.selectedSlot), 0);
  state.selectedSlot = slots[(idx + 1) % slots.length];
  renderDoctorDetail();

  pushMessage(
    "bot",
    `Đã chuyển sang khung giờ **${state.selectedSlot}** với ${doc.name || doc.doctor_name}.\nBạn có muốn xác nhận lịch này không?`,
    "suggest_slot"
  );
}

async function sendQuickReply(text) {
  pushMessage("user", text);
  await callChatAPI(text);
}

function confirmAppointment() {
  const doc = currentDoctor();
  if (!doc || !state.selectedSlot) {
    return;
  }

  const now = new Date();
  const dateLabel = now.toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

  state.currentStep = "confirmed";
  pushMessage(
    "bot",
    `Đã xác nhận lịch thành công!\nBác sĩ: ${doc.name || doc.doctor_name}\nChuyên khoa: ${doc.specialty || ""}\nThời gian: ${dateLabel} lúc ${state.selectedSlot}\nPhòng khám: ${doc.clinic || doc.workplace || ""}`,
    "confirmed"
  );
}

async function callChatAPI(userText) {
  try {
    const doc = currentDoctor();
    const doctorContext = doc
      ? `Bác sĩ: ${doc.name || doc.doctor_name} | Chuyên khoa: ${doc.specialty || ""} | Phòng khám: ${doc.clinic || doc.workplace || ""} | Khung giờ có sẵn: ${(doc.slots || []).join(", ")}`
      : "";

    const result = await apiPost("/chat", {
      message: userText,
      history: state.history,
      doctor_context: doctorContext,
      current_step: state.currentStep || "",
    });

    state.history.push({ role: "user", content: userText });
    state.history.push({ role: "assistant", content: result.message || "" });
    state.currentStep = result.step || "";

    if (result.step === "analyze") {
      state.suggestedDoctors = result.doctor_suggestion || result.suggestions || [];
      state.selectedDoctorIndex = 0;
      state.selectedSlot = state.suggestedDoctors[0]?.slots?.[0] || null;
      renderDoctorList();
      renderDoctorDetail();
    } else if (result.step === "ask_symptom" || result.step === "greeting") {
      // Greeting/small-talk must not show stale doctor suggestions.
      state.suggestedDoctors = [];
      state.selectedDoctorIndex = 0;
      state.selectedSlot = null;
      renderDoctorList();
      renderDoctorDetail();
    }

    pushMessage("bot", result.message || "", result.step || "");
  } catch {
    pushMessage("bot", "Không thể kết nối đến server. Vui lòng thử lại sau.");
  }
}

function _parseTimeInput(text) {
  const m = text.match(/\b(\d{1,2})[h:](\d{0,2})\b/i);
  if (!m) return null;
  const hour = parseInt(m[1], 10);
  if (hour < 0 || hour > 23) return null;
  return hour * 60 + parseInt(m[2] || "0", 10);
}

function _pickSlotByMinutes(minutes) {
  const doc = currentDoctor();
  if (!doc) return null;
  let best = null, bestDiff = Infinity;
  for (const s of (doc.slots || [])) {
    const [h, mn] = s.split(":").map(Number);
    const diff = Math.abs(h * 60 + (mn || 0) - minutes);
    if (diff < bestDiff) { bestDiff = diff; best = s; }
  }
  return best;
}

async function handleSubmit(event) {
  event.preventDefault();
  const inputText = el.chatInput.value.trim();
  if (!inputText) {
    return;
  }

  // Khi đang bước chọn/xác nhận giờ mà user gõ thời gian cụ thể → xử lý local
  if (state.currentStep === "ask_time" || state.currentStep === "suggest_slot") {
    const minutes = _parseTimeInput(inputText);
    if (minutes !== null) {
      const slot = _pickSlotByMinutes(minutes);
      const doc  = currentDoctor();
      el.chatInput.value = "";
      pushMessage("user", inputText);
      if (slot && doc) {
        state.selectedSlot = slot;
        renderDoctorDetail();
        state.currentStep = "suggest_slot";
        pushMessage(
          "bot",
          `Khung giờ **${slot}** còn trống với bác sĩ ${doc.name || doc.doctor_name}.\nBạn có muốn xác nhận lịch này không?`,
          "suggest_slot"
        );
      } else {
        pushMessage("bot", "Không tìm thấy khung giờ phù hợp. Vui lòng chọn buổi sáng hoặc buổi chiều.", "ask_time");
      }
      return;
    }
  }

  pushMessage("user", inputText);
  el.chatInput.value = "";
  await callChatAPI(inputText);
}

function resetChat() {
  state.messages = [];
  state.history = [];
  state.currentStep = "";
  state.suggestedDoctors = [];
  state.selectedDoctorIndex = 0;
  state.selectedSlot = null;
  renderDoctorList();
  renderDoctorDetail();
  pushMessage(
    "bot",
    "Xin chào! Bạn hãy mô tả triệu chứng để mình tìm chuyên khoa và bác sĩ phù hợp nhé."
  );
}

function bindEvents() {
  el.chatForm.addEventListener("submit", handleSubmit);
  el.newChatBtn.addEventListener("click", resetChat);

  el.prevDoctor.addEventListener("click", () => {
    const total = state.suggestedDoctors.length;
    if (!total) {
      return;
    }

    state.selectedDoctorIndex = (state.selectedDoctorIndex - 1 + total) % total;
    const doc = currentDoctor();
    if (doc && !(doc.slots || []).includes(state.selectedSlot)) {
      state.selectedSlot = (doc.slots || [])[0] || null;
    }
    renderDoctorList();
    renderDoctorDetail();
  });

  el.nextDoctor.addEventListener("click", () => {
    const total = state.suggestedDoctors.length;
    if (!total) {
      return;
    }

    state.selectedDoctorIndex = (state.selectedDoctorIndex + 1) % total;
    const doc = currentDoctor();
    if (doc && !(doc.slots || []).includes(state.selectedSlot)) {
      state.selectedSlot = (doc.slots || [])[0] || null;
    }
    renderDoctorList();
    renderDoctorDetail();
  });
}

function init() {
  renderDoctorList();
  renderDoctorDetail();
  bindEvents();
  resetChat();
}

init();
