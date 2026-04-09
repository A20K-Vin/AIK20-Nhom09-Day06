const doctors = [
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
    keys: ["ho", "sot", "viem hong", "kho tho", "dom"],
  },
  {
    specialty: "Than kinh",
    keys: ["dau dau", "choang", "te", "mat ngu", "chong mat"],
  },
];

const state = {
  messages: [],
  suggestedDoctors: doctors.slice(0, 3),
  selectedDoctorIndex: 0,
  selectedSlot: doctors[0].slots[0],
  appointments: [],
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

function detectSpecialty(symptomText) {
  const normalized = symptomText.toLowerCase();

  const found = specialtyKeywords.find((group) =>
    group.keys.some((key) => normalized.includes(key))
  );

  return found ? found.specialty : "Noi tong quat";
}

function getSuggestedDoctorsBySpecialty(specialty) {
  const exact = doctors.filter((doc) => doc.specialty === specialty);
  if (exact.length >= 2) {
    return exact;
  }

  const mixed = [
    ...exact,
    ...doctors.filter((doc) => doc.specialty !== specialty).slice(0, 2),
  ];

  return mixed;
}

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
      li.innerHTML = `<strong>${item.timeLabel} - ${item.slot}</strong><span>${item.doctor} | ${item.specialty}</span>`;
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
      li.className = `consult-session ${
        item.id === state.activeSessionId ? "active" : ""
      }`;
      li.innerHTML = `<strong>${item.symptom}</strong><span>${item.summary} (${item.time})</span>`;

      li.addEventListener("click", () => {
        state.activeSessionId = item.id;
        state.messages = cloneMessages(item.messages);
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
    chip.className = `doctor-chip ${
      index === state.selectedDoctorIndex ? "active" : ""
    }`;
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

  const useDoctorBtn = document.getElementById("doctors-action");
  useDoctorBtn.addEventListener("click", () => {
    pushMessage(
      "bot",
      `Da cap nhat de xuat theo lua chon cua ban.\nBac si: ${doc.name}\nGio kham: ${state.selectedSlot}`,
      true
    );
  });
}

function chooseAnotherSuggestion() {
  const nextDoctorIndex =
    (state.selectedDoctorIndex + 1) % state.suggestedDoctors.length;

  state.selectedDoctorIndex = nextDoctorIndex;
  const doc = currentDoctor();
  const slotIndex = doc.slots.indexOf(state.selectedSlot);
  const nextSlot = doc.slots[(slotIndex + 1 + doc.slots.length) % doc.slots.length];
  state.selectedSlot = nextSlot;

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

function confirmAppointment() {
  const doc = currentDoctor();

  const now = new Date();
  const dateLabel = now.toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

  const appointment = {
    doctor: doc.name,
    specialty: doc.specialty,
    slot: state.selectedSlot,
    timeLabel: dateLabel,
  };

  state.appointments.push(appointment);

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

function generateBotSuggestionFromInput(inputText) {
  const specialty = detectSpecialty(inputText);
  state.suggestedDoctors = getSuggestedDoctorsBySpecialty(specialty);
  state.selectedDoctorIndex = 0;
  state.selectedSlot = state.suggestedDoctors[0].slots[0];

  renderDoctorList();
  renderDoctorDetail();

  pushMessage("bot", currentSuggestionText(), true);
  syncActiveSession({
    symptom: inputText,
    summary: "Da de xuat khoa va lich kham.",
    time: "Vua xong",
  });
}

function handleSubmit(event) {
  event.preventDefault();
  const inputText = el.chatInput.value.trim();

  if (!inputText) {
    return;
  }

  state.latestSymptom = inputText;
  renderLatestSymptom();
  state.messages = [];
  renderMessages();
  startNewSession(inputText);

  pushMessage("user", inputText);
  el.chatInput.value = "";

  setTimeout(() => {
    generateBotSuggestionFromInput(inputText);
  }, 380);
}

function bindEvents() {
  el.chatForm.addEventListener("submit", handleSubmit);

  el.prevDoctor.addEventListener("click", () => {
    const total = state.suggestedDoctors.length;
    state.selectedDoctorIndex = (state.selectedDoctorIndex - 1 + total) % total;
    if (!currentDoctor().slots.includes(state.selectedSlot)) {
      state.selectedSlot = currentDoctor().slots[0];
    }
    renderDoctorList();
    renderDoctorDetail();
  });

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

function init() {
  pushMessage(
    "bot",
    "Chao ban, minh la tro ly dat lich phong kham.\nBan co the mo ta trieu chung de minh de xuat khoa, bac si va lich kham phu hop."
  );

  renderLatestSymptom();
  renderAppointments();
  renderConsultHistory();
  renderDoctorList();
  renderDoctorDetail();
  bindEvents();
}

init();
