const API_BASE = "http://localhost:8000/api";

const fallbackDoctors = [
  {
    id: "tim-01",
    name: "ThS.BS Nguyen Minh Chau",
    specialty: "Noi tim mach",
    degree: "Thac si Y khoa, CKI Noi tim mach",
    clinic: "Phong kham Tim mach - Tang 3",
    rating: 4.9,
    image:
      "https://images.unsplash.com/photo-1537368910025-700350fe46c7?auto=format&fit=crop&w=420&q=80",
    slots: ["08:30", "09:15", "10:00", "14:00"],
  },
  {
    id: "hohap-01",
    name: "BS Le Hoang Ngan",
    specialty: "Noi ho hap",
    degree: "Bac si Noi tru Ho hap",
    clinic: "Khu kham Tong quat - Phong 12",
    rating: 4.7,
    image:
      "https://images.unsplash.com/photo-1614608682850-e0d6ed316d47?auto=format&fit=crop&w=420&q=80",
    slots: ["09:00", "10:30", "13:30", "15:00"],
  },
  {
    id: "than-kinh-01",
    name: "PGS.TS Tran Thi Bich An",
    specialty: "Than kinh",
    degree: "Pho giao su, Tien si Than kinh",
    clinic: "Khoa Than kinh - Phong 21",
    rating: 4.95,
    image:
      "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&w=420&q=80",
    slots: ["08:45", "11:00", "14:30", "16:15"],
  },
  {
    id: "tongquat-01",
    name: "BS Pham Quoc Huy",
    specialty: "Noi tong quat",
    degree: "Bac si Da khoa",
    clinic: "Phong kham Tong quat - Tang 1",
    rating: 4.6,
    image:
      "https://images.unsplash.com/photo-1622253692010-333f2da6031d?auto=format&fit=crop&w=420&q=80",
    slots: ["07:45", "09:45", "13:00", "16:00"],
  },
];

const specialtyKeywords = [
  {
    specialty: "Noi tim mach",
    keys: ["tim", "nguc", "kho tho", "danh trong nguc"],
  },
  {
    specialty: "Noi ho hap",
    keys: ["ho", "sot", "viem hong", "dom", "kho tho"],
  },
  {
    specialty: "Than kinh",
    keys: ["dau dau", "chong mat", "te", "mat ngu", "choang"],
  },
];

// ── State ────────────────────────────────────────────────────────────────────

const state = {
  messages: [],
  suggestedDoctors: [],
  selectedDoctorIndex: 0,
  selectedSlot: null,
  appointments: [],
  pendingAppointment: null,
  chatSessions: [
    {
      id: "session-mock-1",
      symptom: "Met moi, kho ngu 2 ngay",
      summary: "Da goi y khoa Than kinh va lich 14:30.",
      time: "Hom qua",
      messages: [
        {
          id: "mock-msg-1",
          sender: "user",
          text: "Gan day toi met moi va kho ngu.",
          withActions: false,
        },
        {
          id: "mock-msg-2",
          sender: "bot",
          text: "Ban nen kham khoa Than kinh.\nBac si de xuat: PGS.TS Tran Thi Bich An.\nKhung gio phu hop: 14:30 hom nay.",
          withActions: true,
        },
      ],
    },
  ],
  activeSessionId: null,
  latestSymptom: "Chua co mo ta trieu chung.",
};

const el = {
  chatFeed: document.getElementById("chat-feed"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  newChatBtn: document.getElementById("new-chat-btn"),
  bookingModal: document.getElementById("booking-modal"),
  bookingForm: document.getElementById("booking-form"),
  bookingClose: document.getElementById("booking-close"),
  patientName: document.getElementById("patient-name"),
  patientGender: document.getElementById("patient-gender"),
  patientDob: document.getElementById("patient-dob"),
  patientPhone: document.getElementById("patient-phone"),
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

function detectSpecialty(symptomText) {
  const normalized = (symptomText || "").toLowerCase();
  const found = specialtyKeywords.find((group) =>
    group.keys.some((key) => normalized.includes(key))
  );
  return found ? found.specialty : "Noi tong quat";
}

function getSuggestedDoctorsBySpecialty(specialty) {
  const exact = fallbackDoctors.filter((doc) => doc.specialty === specialty);
  if (exact.length >= 2) {
    return exact;
  }
  return [
    ...exact,
    ...fallbackDoctors.filter((doc) => doc.specialty !== specialty).slice(0, 2),
  ];
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
  const newMessage = {
    id: `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    sender,
    text,
    withActions,
  };

  state.messages.push(newMessage);

  syncActiveSession();
  appendMessageToFeed(newMessage);
}

function cloneMessages(messages) {
  return messages.map((msg) => ({ ...msg }));
}

function syncActiveSession(overrides = {}) {
  if (!state.activeSessionId) {
    return;
  }

  const target = state.chatSessions.find(
    (session) => session.id === state.activeSessionId
  );

  if (!target) {
    return;
  }

  target.messages = cloneMessages(state.messages);

  if (overrides.symptom) {
    target.symptom = overrides.symptom;
  }
  if (overrides.summary) {
    target.summary = overrides.summary;
  }
  if (overrides.time) {
    target.time = overrides.time;
  }

  renderConsultHistory();
}

function startNewSession(symptomText) {
  const newSession = {
    id: `session-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    symptom: symptomText,
    summary: "Dang tu van.",
    time: "Vua xong",
    messages: [],
  };

  state.chatSessions.push(newSession);
  state.activeSessionId = newSession.id;
  renderConsultHistory();
}

function startManualNewChat() {
  state.activeSessionId = null;
  state.messages = [];
  state.latestSymptom = "Chua co mo ta trieu chung.";
  state.pendingAppointment = null;

  renderMessages();
  renderLatestSymptom();
  renderConsultHistory();

  pushMessage(
    "bot",
    `Da tao doan chat moi.
Ban co the mo ta trieu chung de minh de xuat khoa, bac si va lich kham phu hop.`
  );
}

function openBookingModal() {
  if (!el.bookingModal || !el.bookingForm) {
    return;
  }

  el.bookingForm.reset();
  el.bookingModal.classList.add("open");
  el.bookingModal.setAttribute("aria-hidden", "false");
}

function closeBookingModal() {
  if (!el.bookingModal) {
    return;
  }

  el.bookingModal.classList.remove("open");
  el.bookingModal.setAttribute("aria-hidden", "true");
  state.pendingAppointment = null;
}

function handleBookingSubmit(event) {
  event.preventDefault();

  if (!state.pendingAppointment) {
    closeBookingModal();
    return;
  }

  const patientName = (el.patientName?.value || "").trim();
  const patientGender = (el.patientGender?.value || "").trim();
  const patientDob = (el.patientDob?.value || "").trim();
  const patientPhone = (el.patientPhone?.value || "").trim();

  if (!patientName || !patientGender || !patientDob || !patientPhone) {
    return;
  }

  const appointment = {
    ...state.pendingAppointment,
    patient: {
      name: patientName,
      gender: patientGender,
      dob: patientDob,
      phone: patientPhone,
    },
  };

  state.appointments.push(appointment);
  renderAppointments();

  pushMessage(
    "bot",
    `Da xac nhan lich thanh cong.\nHen gap ${patientName} ngay ${appointment.timeLabel} luc ${appointment.slot} voi ${appointment.doctor}.`
  );

  syncActiveSession({
    summary: `Da dat voi ${appointment.doctor} luc ${appointment.slot}`,
    time: "Vua xong",
  });

  closeBookingModal();
}

function currentDoctor() {
  return state.suggestedDoctors[state.selectedDoctorIndex];
}

function currentSuggestionText() {
  const doc = currentDoctor();
  return [
    `Du tren trieu chung, ban nen kham khoa ${doc.specialty}.`,
    `Bac si de xuat: ${doc.name} (${doc.rating}/5).`,
    `Khung gio phu hop: ${state.selectedSlot} hom nay tai ${doc.clinic}.`,
  ].join("\n");
}

function createMessageBubble(msg, shouldAnimate = true) {
  const bubble = document.createElement("article");
  bubble.className = `chat-bubble ${msg.sender}`;

  if (!shouldAnimate) {
    bubble.classList.add("no-anim");
  }

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

  return bubble;
}

function appendMessageToFeed(msg, shouldAnimate = true) {
  if (!el.chatFeed) {
    return;
  }

  el.chatFeed.appendChild(createMessageBubble(msg, shouldAnimate));
  el.chatFeed.scrollTop = el.chatFeed.scrollHeight;
}

function renderMessages() {
  if (!el.chatFeed) {
    return;
  }

  el.chatFeed.innerHTML = "";

  state.messages.forEach((msg) => {
    appendMessageToFeed(msg, false);
  });
}

function renderAppointments() {
  if (!el.appointmentList || !el.appointmentCount) {
    return;
  }

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
  if (!el.consultHistory) {
    return;
  }

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
  if (!el.latestSymptomText) {
    return;
  }

  el.latestSymptomText.textContent = state.latestSymptom;
}

function renderDoctorList() {
  if (!el.doctorList || !el.doctorTotal || !el.doctorIndex) {
    return;
  }

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
  if (!el.doctorDetail) {
    return;
  }

  const doc = currentDoctor();
  if (!doc) {
    return;
  }

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
  if (!slotRow) {
    return;
  }

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

  const useDoctorBtn = document.getElementById("doctors-action");
  if (!useDoctorBtn) {
    return;
  }

  useDoctorBtn.addEventListener("click", () => {
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

  state.pendingAppointment = {
    doctor: doc.name,
    specialty: doc.specialty,
    slot: state.selectedSlot,
    timeLabel: dateLabel,
  };

  openBookingModal();
}

function generateBotSuggestionFromInput(inputText, shouldUpdateSymptom = false) {
  const specialty = detectSpecialty(inputText);
  state.suggestedDoctors = getSuggestedDoctorsBySpecialty(specialty);
  state.selectedDoctorIndex = 0;
  state.selectedSlot = state.suggestedDoctors[0]?.slots[0] ?? null;

  renderDoctorList();
  renderDoctorDetail();

  pushMessage("bot", currentSuggestionText(), true);

  const updates = {
    summary: "Da de xuat khoa va lich kham.",
    time: "Vua xong",
  };

  if (shouldUpdateSymptom) {
    updates.symptom = inputText;
  }

  syncActiveSession(updates);
}

// ── Event handling ────────────────────────────────────────────────────────────

async function handleSubmit(event) {
  event.preventDefault();
  const inputText = el.chatInput.value.trim();

  if (!inputText) {
    return;
  }

  const shouldCreateSession = !state.activeSessionId;
  if (shouldCreateSession) {
    startNewSession(inputText);
  }

  state.latestSymptom = inputText;
  renderLatestSymptom();

  pushMessage("user", inputText);
  el.chatInput.value = "";

  setTimeout(() => {
    generateBotSuggestionFromInput(inputText, shouldCreateSession);
  }, 380);
}

function bindEvents() {
  if (el.chatForm) {
    el.chatForm.addEventListener("submit", handleSubmit);
  }
  if (el.newChatBtn) {
    el.newChatBtn.addEventListener("click", startManualNewChat);
  }

  if (el.bookingForm) {
    el.bookingForm.addEventListener("submit", handleBookingSubmit);
  }

  if (el.bookingClose) {
    el.bookingClose.addEventListener("click", closeBookingModal);
  }

  if (el.bookingModal) {
    el.bookingModal.addEventListener("click", (event) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.dataset.closeModal === "true") {
        closeBookingModal();
      }
    });
  }

  if (el.prevDoctor) {
    el.prevDoctor.addEventListener("click", () => {
      const total = state.suggestedDoctors.length;
      state.selectedDoctorIndex = (state.selectedDoctorIndex - 1 + total) % total;
      if (!currentDoctor().slots.includes(state.selectedSlot)) {
        state.selectedSlot = currentDoctor().slots[0];
      }
      renderDoctorList();
      renderDoctorDetail();
    });
  }

  if (el.nextDoctor) {
    el.nextDoctor.addEventListener("click", () => {
      const total = state.suggestedDoctors.length;
      state.selectedDoctorIndex = (state.selectedDoctorIndex + 1) % total;
      if (!currentDoctor().slots.includes(state.selectedSlot)) {
        state.selectedSlot = currentDoctor().slots[0];
      }
      renderDoctorList();
      renderDoctorDetail();
    });
  }
}

function init() {
  // Bind input events first so chat submit still works even if a render section fails.
  bindEvents();

  pushMessage(
    "bot",
    "Chao ban, minh la tro ly dat lich phong kham.\nBan co the mo ta trieu chung de minh de xuat khoa, bac si va lich kham phu hop."
  );

  renderLatestSymptom();
  renderAppointments();
  renderConsultHistory();
  renderDoctorList();
  renderDoctorDetail();
}

init();
