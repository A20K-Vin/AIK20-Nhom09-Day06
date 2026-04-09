const API_BASE = "http://localhost:8000/api";

// ── State ────────────────────────────────────────────────────────────────────

const state = {
  messages: [],
  suggestedDoctors: [],
  selectedDoctorIndex: 0,
  selectedSlot: null,
  appointments: [],
  chatSessions: [],
  activeSessionId: null,
  latestSymptom: "Chua co mo ta trieu chung.",
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
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json();
}

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

async function apiPatch(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${path} failed: ${res.status}`);
  return res.json();
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function currentDoctor() {
  return state.suggestedDoctors[state.selectedDoctorIndex];
}

function currentSuggestionText(specialty) {
  const doc = currentDoctor();
  return [
    `Du tren trieu chung, ban nen kham khoa ${specialty}.`,
    `Bac si de xuat: ${doc.name} (${doc.rating}/5).`,
    `Khung gio phu hop: ${state.selectedSlot} hom nay tai ${doc.clinic}.`,
  ].join("\n");
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
    if (overrides.time) local.time = overrides.time;
  }

  try {
    await apiPatch(`/sessions/${state.activeSessionId}`, {
      messages: state.messages,
      ...overrides,
    });
  } catch {
    // non-critical, UI already updated locally
  }

  renderConsultHistory();
}

async function startNewSession(symptomText) {
  const session = await apiPost("/sessions", { symptom: symptomText });
  state.chatSessions.push(session);
  state.activeSessionId = session.id;
  renderConsultHistory();
}

async function loadSessions() {
  try {
    const sessions = await apiGet("/sessions?userId=guest");
    state.chatSessions = sessions;
    renderConsultHistory();
  } catch {
    // backend not yet available — skip
  }
}

async function loadAppointments() {
  try {
    const appts = await apiGet("/appointments?userId=guest");
    state.appointments = appts;
    renderAppointments();
  } catch {
    // backend not yet available — skip
  }
}

// ── Render ────────────────────────────────────────────────────────────────────

function pushMessage(sender, text, withActions = false) {
  state.messages.push({
    id: `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    sender,
    text,
    withActions,
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

    if (msg.withActions) {
      const actions = document.createElement("div");
      actions.className = "chat-actions";

      const confirmBtn = document.createElement("button");
      confirmBtn.className = "confirm-btn";
      confirmBtn.type = "button";
      confirmBtn.textContent = "Xac nhan lich";
      confirmBtn.addEventListener("click", confirmAppointment);

      const otherBtn = document.createElement("button");
      otherBtn.className = "other-btn";
      otherBtn.type = "button";
      otherBtn.textContent = "Chon lich khac";
      otherBtn.addEventListener("click", chooseAnotherSuggestion);

      actions.append(confirmBtn, otherBtn);
      bubble.appendChild(actions);
    }

    el.chatFeed.appendChild(bubble);
  });

  el.chatFeed.scrollTop = el.chatFeed.scrollHeight;
}

function renderAppointments() {
  el.appointmentList.innerHTML = "";
  el.appointmentCount.textContent = `${state.appointments.length} lich`;

  if (state.appointments.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Ban chua xac nhan lich nao.";
    el.appointmentList.appendChild(empty);
    return;
  }

  state.appointments
    .slice()
    .reverse()
    .forEach((item) => {
      const li = document.createElement("li");
      li.innerHTML = `<strong>${item.date} - ${item.slot}</strong><span>${item.doctor} | ${item.specialty}</span>`;
      el.appointmentList.appendChild(li);
    });
}

function renderConsultHistory() {
  el.consultHistory.innerHTML = "";

  state.chatSessions
    .slice()
    .reverse()
    .forEach((item) => {
      const li = document.createElement("li");
      li.className = `consult-session ${item.id === state.activeSessionId ? "active" : ""}`;
      li.innerHTML = `<strong>${item.symptom}</strong><span>${item.summary} (${item.time})</span>`;

      li.addEventListener("click", () => {
        state.activeSessionId = item.id;
        state.messages = cloneMessages(item.messages || []);
        state.latestSymptom = item.symptom;
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
      if (!doc.slots.includes(state.selectedSlot)) {
        state.selectedSlot = doc.slots[0];
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
  if (!currentDoctor()) return;
  const doc = currentDoctor();

  el.doctorDetail.innerHTML = `
    <div class="doctor-hero">
      <img src="${doc.image}" alt="Hinh bac si ${doc.name}" />
      <div>
        <h3>${doc.name}</h3>
        <p>${doc.specialty}</p>
        <p>${doc.degree}</p>
      </div>
    </div>

    <div class="info-grid">
      <div>
        <p>Phong kham</p>
        <strong>${doc.clinic}</strong>
      </div>
      <div>
        <p>Danh gia</p>
        <strong>${doc.rating}/5</strong>
      </div>
    </div>

    <div class="slot-wrap">
      <p>Khung gio trong</p>
      <div id="slot-row" class="slot-row"></div>
    </div>

    <button id="doctors-action" type="button">Chon bac si nay</button>
  `;

  const slotRow = document.getElementById("slot-row");
  doc.slots.forEach((slot) => {
    const slotBtn = document.createElement("button");
    slotBtn.type = "button";
    slotBtn.className = `slot-btn ${slot === state.selectedSlot ? "active" : ""}`;
    slotBtn.textContent = slot;

    slotBtn.addEventListener("click", () => {
      state.selectedSlot = slot;
      renderDoctorDetail();
    });

    slotRow.appendChild(slotBtn);
  });

  document.getElementById("doctors-action").addEventListener("click", () => {
    pushMessage(
      "bot",
      `Da cap nhat de xuat theo lua chon cua ban.\nBac si: ${doc.name}\nGio kham: ${state.selectedSlot}`,
      true
    );
  });
}

// ── Actions ───────────────────────────────────────────────────────────────────

function chooseAnotherSuggestion() {
  const total = state.suggestedDoctors.length;
  state.selectedDoctorIndex = (state.selectedDoctorIndex + 1) % total;
  const doc = currentDoctor();
  const idx = doc.slots.indexOf(state.selectedSlot);
  state.selectedSlot = doc.slots[(idx + 1) % doc.slots.length];

  renderDoctorList();
  renderDoctorDetail();

  pushMessage(
    "bot",
    `Da tim lich khac cho ban.\nBac si: ${doc.name}\nKhung gio moi: ${state.selectedSlot}`,
    true
  );

  syncActiveSession({
    summary: `Da doi sang ${doc.name} luc ${state.selectedSlot}.`,
    time: "Vua xong",
  });
}

async function confirmAppointment() {
  const doc = currentDoctor();
  const now = new Date();
  const dateLabel = now.toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
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
    // fallback: store locally if API fails
    state.appointments.push({
      doctor: doc.name,
      specialty: doc.specialty,
      slot: state.selectedSlot,
      date: dateLabel,
    });
  }

  renderAppointments();

  pushMessage(
    "bot",
    `Da xac nhan lich thanh cong.\nHen gap ban ngay ${dateLabel} luc ${state.selectedSlot} voi ${doc.name}.`
  );

  syncActiveSession({
    summary: `Da dat voi ${doc.name} luc ${state.selectedSlot}`,
    time: "Vua xong",
  });
}

async function generateBotSuggestion(inputText) {
  let botMessage = "";
  let doctors = [];

  try {
    const result = await apiPost("/chat", { message: inputText });
    botMessage = result.message;
    doctors = result.doctor_suggestion;
  } catch {
    pushMessage("bot", "Khong the ket noi den server. Vui long thu lai sau.");
    return;
  }

  state.suggestedDoctors = doctors;
  state.selectedDoctorIndex = 0;
  state.selectedSlot = doctors[0]?.slots[0] ?? null;

  renderDoctorList();
  renderDoctorDetail();
  pushMessage("bot", botMessage, true);

  syncActiveSession({
    symptom: inputText,
    summary: "Da de xuat khoa va lich kham.",
    time: "Vua xong",
  });
}

// ── Event handling ────────────────────────────────────────────────────────────

async function handleSubmit(event) {
  event.preventDefault();
  const inputText = el.chatInput.value.trim();
  if (!inputText) return;

  state.latestSymptom = inputText;
  renderLatestSymptom();
  state.messages = [];
  renderMessages();

  await startNewSession(inputText);

  pushMessage("user", inputText);
  el.chatInput.value = "";

  setTimeout(() => generateBotSuggestion(inputText), 380);
}

function bindEvents() {
  el.chatForm.addEventListener("submit", handleSubmit);

  el.prevDoctor.addEventListener("click", () => {
    const total = state.suggestedDoctors.length;
    if (!total) return;
    state.selectedDoctorIndex = (state.selectedDoctorIndex - 1 + total) % total;
    if (!currentDoctor().slots.includes(state.selectedSlot)) {
      state.selectedSlot = currentDoctor().slots[0];
    }
    renderDoctorList();
    renderDoctorDetail();
  });

  el.nextDoctor.addEventListener("click", () => {
    const total = state.suggestedDoctors.length;
    if (!total) return;
    state.selectedDoctorIndex = (state.selectedDoctorIndex + 1) % total;
    if (!currentDoctor().slots.includes(state.selectedSlot)) {
      state.selectedSlot = currentDoctor().slots[0];
    }
    renderDoctorList();
    renderDoctorDetail();
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  pushMessage(
    "bot",
    "Chao ban, minh la tro ly dat lich phong kham.\nBan co the mo ta trieu chung de minh de xuat khoa, bac si va lich kham phu hop."
  );

  renderLatestSymptom();
  renderAppointments();
  bindEvents();

  await Promise.all([loadSessions(), loadAppointments()]);
}

init();
