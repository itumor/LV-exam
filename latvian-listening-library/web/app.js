const menu = document.querySelector("#menu");
const search = document.querySelector("#search");
const title = document.querySelector("#title");
const subtitle = document.querySelector("#subtitle");
const audio = document.querySelector("#audio");
const lvText = document.querySelector("#lvText");
const enText = document.querySelector("#enText");
const lvLink = document.querySelector("#lvLink");
const enLink = document.querySelector("#enLink");
const statusBadge = document.querySelector("#statusBadge");
const previousButton = document.querySelector("#prev");
const nextButton = document.querySelector("#next");

const levelLabels = {
  A1: "A1 Klausīšanās",
  A2: "A2 Klausīšanās",
};

const visualLessons = [
  "Prieks iepazīties!",
  "No visas pasaules",
  "Pilsētā un laukos",
  "Mana māja un ģimene",
  "Kājām, ar trolejbusu, ar lidmašīnu",
  "Ikdienas darbi",
  "Iepirkšanās",
  "Labu apetīti!",
  "Brīvais laiks",
  "Es ceļoju",
  "Esi vesels!",
  "Mācības un darbs",
];

let catalog = [];
let filtered = [];
let selectedIndex = -1;

const SCENARIOS = [
  {
    id: "school-call",
    title: "Zvana uz skolu",
    titleEn: "School Call",
    description: "Communicating with teachers about your child's progress, attendance, or schedule.",
    category: "family",
    vocabulary: ["skolotājs", "stunda", "mājasdarbs", "atzīme", "sapulce", "kavējums"],
    phrases: [
      { lv: "Labdien, es gribētu runāt ar savas meitas skolotāju.", en: "Hello, I'd like to speak with my daughter's teacher.", context: "Calling to speak with a teacher" },
      { lv: "Kā manas meitas attīstība šajā semestrī?", en: "How is my daughter's progress this semester?", context: "Asking about academic progress" },
    ],
    survivalPhrases: [
      { lv: "Vai es varu runāt ar kādu no skolas?", en: "Can I speak with someone from the school?", context: "General inquiry" },
      { lv: "Kurš ir mans bērna klases audzinātājs?", en: "Who is my child's class teacher?", context: "Asking about teacher" },
    ]
  },
  {
    id: "kindergarten",
    title: "Bērnudārzs",
    titleEn: "Kindergarten",
    description: "Enrolling your child, discussing daily routines, and communicating with caregivers.",
    category: "family",
    vocabulary: ["bērnudārzs", "audzinātāja", "vecāki", "rotas laiks", "dienas grafiks", "veselība"],
    phrases: [
      { lv: "Kur ir manas meitas istaba?", en: "Where is my daughter's room?", context: "Finding the classroom" },
      { lv: "Vai mans bērns ir labi ēdis?", en: "Did my child eat well?", context: "Asking about meals" },
    ],
    survivalPhrases: [
      { lv: "Kad ir sapulce?", en: "When is the meeting?", context: "Asking about parent meeting" },
      { lv: "Man ir steidzams jautājums par manu bērnu.", en: "I have an urgent question about my child.", context: "Urgent inquiry" },
    ]
  },
  {
    id: "doctor",
    title: "Pie ārsta",
    titleEn: "Doctor Appointment",
    description: "Making appointments, describing symptoms, understanding prescriptions and medical instructions.",
    category: "health",
    vocabulary: ["ārsts", "slimība", "simptomi", "recepte", "analīzes", "uzņemšana"],
    phrases: [
      { lv: "Man ir sāpējusi galva un drudzis.", en: "I have a headache and fever.", context: "Describing symptoms" },
      { lv: "Kad man jāatgriežas uz kontroles vizīti?", en: "When do I need to come back for a follow-up?", context: "Follow-up appointment" },
    ],
    survivalPhrases: [
      { lv: "Lūdzu, atkārtojiet vēlreiz.", en: "Please repeat that again.", context: "Asking for repetition" },
      { lv: "Es nesapratu. Vai jūs varat izskaidrot?", en: "I didn't understand. Can you explain?", context: "Asking for clarification" },
      { lv: "Kur ir aptieka?", en: "Where is the pharmacy?", context: "Finding pharmacy" },
    ]
  },
  {
    id: "pharmacy",
    title: "Aptieka",
    titleEn: "Pharmacy",
    description: "Buying medicine, asking for advice, understanding dosage instructions.",
    category: "health",
    vocabulary: ["aptieka", "zāles", "devas", "recepte", "bezrecepšu", "pretsāpju"],
    phrases: [
      { lv: "Man ir nepieciešamas pretsāpju zāles.", en: "I need pain relief medication.", context: "Asking for medication" },
      { lv: "Kā šīs zāles jālieto?", en: "How should I take these medicine?", context: "Dosage instructions" },
    ],
    survivalPhrases: [
      { lv: "Vai jums ir kaut kas pret alerģiju?", en: "Do you have something for allergies?", context: "Allergy medication" },
      { lv: "Šīs zāles ir bez receptes?", en: "These medicine are over-the-counter?", context: "OTC medicine" },
    ]
  },
  {
    id: "government",
    title: "Valsts iestāde",
    titleEn: "Government Office",
    description: "Visiting municipal offices, population registry, social services.",
    category: "bureaucracy",
    vocabulary: ["pagrieziens", "reģistrs", "dokumenti", "veidlapa", "rinda", "apstiprinājums"],
    phrases: [
      { lv: "Kur es varu reģistrēt dzīvesvietu?", en: "Where can I register my residence?", context: "Registration" },
      { lv: "Kādi dokumenti man ir nepieciešami?", en: "What documents do I need?", context: "Required documents" },
    ],
    survivalPhrases: [
      { lv: "Kur ir numuriņš?", en: "Where is the ticket machine?", context: "Getting a number" },
      { lv: "Vai es varu aizpildīt veidlapu savā valodā?", en: "Can I fill out the form in my language?", context: "Form in native language" },
    ]
  },
  {
    id: "residency",
    title: "Uzturēšanās atļauja",
    titleEn: "Residency Permit",
    description: "Applying for residence permits, extensions, understanding requirements.",
    category: "bureaucracy",
    vocabulary: ["uzturēšanās atļauja", "pielietojums", "dokumentācija", "termiņš", "maksa", "intervija"],
    phrases: [
      { lv: "Es vēlos pieteikties uzturēšanās atļaujai.", en: "I want to apply for a residence permit.", context: "Application" },
      { lv: "Cik ilgi jāgaida lēmums?", en: "How long does it take to get a decision?", context: "Processing time" },
    ],
    survivalPhrases: [
      { lv: "Kur es varu sevi pierakstīt?", en: "Where can I register myself?", context: "Registration" },
      { lv: "Vai nepieciešams tulks?", en: "Is an interpreter needed?", context: "Interpreter needed" },
    ]
  },
  {
    id: "work-meeting",
    title: "Darba sanāksme",
    titleEn: "Work Meeting",
    description: "Participating in professional meetings, understanding tasks, workplace communication.",
    category: "work",
    vocabulary: ["sanāksme", "projekts", "uzdevums", "termiņš", "komanda", "atbalsts"],
    phrases: [
      { lv: "Kāds ir mūsu nākamā projekta grafiks?", en: "What is the schedule for our next project?", context: "Project timeline" },
      { lv: "Vai es varu saņemt šo informāciju rakstiski?", en: "Can I get this information in writing?", context: "Written confirmation" },
    ],
    survivalPhrases: [
      { lv: "Vai jūs varat runāt lēnāk?", en: "Can you speak more slowly?", context: "Speaking slower" },
      { lv: "Atvainojiet, ko jūs domājāt ar...?", en: "Sorry, what did you mean by...?", context: "Clarification" },
    ]
  },
  {
    id: "landlord",
    title: "Īrnieks/īpašnieks",
    titleEn: "Landlord Conversation",
    description: "Renting apartments, discussing repairs, utilities, and lease agreements.",
    category: "bureaucracy",
    vocabulary: ["īrēšana", "īrnieks", "īpašnieks", "dakšas", "skaņojums", "līgums"],
    phrases: [
      { lv: "Vai ir iespēja pagarināt īres līgumu?", en: "Is it possible to extend the lease?", context: "Lease extension" },
      { lv: "Kur ir ūdens skaitītājs?", en: "Where is the water meter?", context: "Utilities" },
    ],
    survivalPhrases: [
      { lv: "Vai varu samaksāt ar pārskaitījumu?", en: "Can I pay by bank transfer?", context: "Payment method" },
      { lv: "Kad varu pārvākties iekšā?", en: "When can I move in?", context: "Moving in" },
    ]
  },
  {
    id: "utilities",
    title: "Rēķini",
    titleEn: "Utilities & Bills",
    description: "Paying electricity, gas, water bills, understanding usage, resolving issues.",
    category: "bureaucracy",
    vocabulary: ["elektrība", "gāze", "ūdens", "patēriņš", "maksa", "rēķins"],
    phrases: [
      { lv: "Kā es varu samaksāt rēķinu tiešsaistē?", en: "How can I pay the bill online?", context: "Online payment" },
      { lv: "Kāpēc šomēnes rēķins ir tik augsts?", en: "Why is this month's bill so high?", context: "High bill inquiry" },
    ],
    survivalPhrases: [
      { lv: "Kur ir manis rēķins?", en: "Where is my bill?", context: "Finding bill" },
      { lv: "Vai varu nomainīt pakalpojumu sniedzēju?", en: "Can I change the service provider?", context: "Provider change" },
    ]
  },
  {
    id: "bank",
    title: "Banka/ Pasta",
    titleEn: "Bank / Post Office",
    description: "Opening accounts, transfers, sending packages, official correspondence.",
    category: "bureaucracy",
    vocabulary: ["konts", "pārskaitījums", "karšu", "ievietošana", "paka", "sūtījums"],
    phrases: [
      { lv: "Es vēlos atvērt kredītkartes kontu.", en: "I want to open a credit card account.", context: "Credit card" },
      { lv: "Cik maksā sūtīt pakotni uz Vāciju?", en: "How much does it cost to send a package to Germany?", context: "Shipping cost" },
    ],
    survivalPhrases: [
      { lv: "Kāda ir jūsu darba laiks?", en: "What are your working hours?", context: "Opening hours" },
      { lv: "Vai jums ir iespēja runāt angliski?", en: "Do you speak English?", context: "Language" },
    ]
  },
  {
    id: "transport",
    title: "Sabiedriskais transports",
    titleEn: "Public Transport",
    description: "Buying tickets, routes, schedules, reporting issues, requesting stops.",
    category: "transport",
    vocabulary: ["autobuss", "tramvajs", "trolejbuss", "biļete", "maršruts", " pietura"],
    phrases: [
      { lv: "Vai šis autobussbrauc uz centru?", en: "Does this bus go to the center?", context: "Route inquiry" },
      { lv: "Kur es varu nopirkt mēnešbiļeti?", en: "Where can I buy a monthly ticket?", context: "Monthly ticket" },
    ],
    survivalPhrases: [
      { lv: "Lūdzu, apstājiet šeit!", en: "Please stop here!", context: "Request stop" },
      { lv: "Es gribētu izkāpt pie nākamās pieturas.", en: "I want to get off at the next stop.", context: "Next stop" },
    ]
  },
  {
    id: "grocery",
    title: "Veikals/Kase",
    titleEn: "Grocery / Cashier",
    description: "Shopping, asking for products, understanding prices, payment methods.",
    category: "shopping",
    vocabulary: ["prece", "cena", "atlaide", "svars", "maksa", "kvīts"],
    phrases: [
      { lv: "Kur es varu atrast maize?", en: "Where can I find bread?", context: "Finding products" },
      { lv: "Vai jums ir biologiska piena?", en: "Do you have organic milk?", context: "Organic products" },
    ],
    survivalPhrases: [
      { lv: "Vai es varu maksāt ar karti?", en: "Can I pay by card?", context: "Card payment" },
      { lv: "Vai varat dot maisiņu?", en: "Can you give me a bag?", context: "Bag request" },
    ]
  }
];

const ASK_TO_REPEAT_PHRASES = [
  { lv: "Lūdzu, atkārtojiet!", en: "Please repeat!", usage: "When you need someone to say something again" },
  { lv: "Es nesapratu.", en: "I didn't understand.", usage: "When the meaning is unclear" },
  { lv: "Vai jūs varat runāt lēnāk?", en: "Can you speak more slowly?", usage: "When speech is too fast" },
  { lv: "Vēlreiz, lūdzu.", en: "One more time, please.", usage: "Polite request for repetition" },
  { lv: "Kā? Ko jūs teicāt?", en: "What? What did you say?", usage: "Informal way to ask for repetition" }
];

const CONFIDENCE_CHECKLIST = [
  "Es varu saprast sveicienu.",
  "Es varu identificēt laiku/datumu/vietu.",
  "Es varu lūgt atkārtot.",
  "Es varu atbildēt ar īsu teikumu."
];

const CATEGORY_FILTERS = {
  family: "Gimene",
  work: "Darbs",
  health: "Veselība",
  bureaucracy: "Birokrātija",
  transport: "Transports",
  shopping: "Iepirkšanās"
};

const PROGRESS_KEY = "latvian_listening_library_progress";
const MODE_KEY = "latvian_listening_library_mode";

let currentMode = localStorage.getItem(MODE_KEY) || "library";
let scenarioProgress = {};

try {
  scenarioProgress = JSON.parse(localStorage.getItem(PROGRESS_KEY)) || {};
} catch {
  scenarioProgress = {};
}

function saveProgress() {
  localStorage.setItem(PROGRESS_KEY, JSON.stringify(scenarioProgress));
}

function getScenarioProgress(scenarioId) {
  return scenarioProgress[scenarioId] || "not_started";
}

function setScenarioProgress(scenarioId, status) {
  scenarioProgress[scenarioId] = status;
  saveProgress();
}

function badgeClass(status) {
  if (status === "completed") return "badge badge-completed";
  if (status === "transcribed only" || status === "translation failed") return "badge badge-transcribed";
  if (status === "failed") return "badge badge-failed";
  return "badge badge-muted";
}

function setText(node, value, fallback) {
  node.textContent = value && value.trim() ? value : fallback;
}

function renderMenu() {
  menu.textContent = "";
  
  if (currentMode === "living") {
    renderLivingInLatviaMenu();
    return;
  }

  for (const level of ["A1", "A2"]) {
    const items = filtered.filter((item) => item.level === level);
    const section = document.createElement("section");
    section.className = "level-section";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "level-toggle";
    toggle.setAttribute("aria-expanded", "true");
    toggle.textContent = `${levelLabels[level]} (${items.length})`;
    const plus = document.createElement("span");
    plus.textContent = "−";
    toggle.appendChild(plus);

    const list = document.createElement("div");
    list.className = "item-list";

    for (const item of items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "audio-item";
      if (filtered[selectedIndex] && filtered[selectedIndex].id === item.id) {
        button.classList.add("active");
      }
      button.addEventListener("click", () => selectItem(filtered.findIndex((candidate) => candidate.id === item.id)));

      const dot = document.createElement("span");
      dot.className = "play-dot";
      const label = document.createElement("span");
      label.textContent = item.title || item.original_filename || "Audio";
      const status = document.createElement("small");
      status.textContent = item.status || "unknown";
      button.append(dot, label, status);
      list.appendChild(button);
    }

    toggle.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!expanded));
      plus.textContent = expanded ? "+" : "−";
      list.hidden = expanded;
    });

    section.append(toggle, list);
    menu.appendChild(section);
  }

  if (filtered.length === 0) {
    visualLessons.forEach((lesson, index) => {
      const card = document.createElement("div");
      card.className = "lesson-card";
      card.textContent = `${index + 1}. ${lesson}`;
      menu.appendChild(card);
    });
  }
}

function renderLivingInLatviaMenu() {
  const modeSection = document.createElement("section");
  modeSection.className = "level-section";

  const backButton = document.createElement("button");
  backButton.type = "button";
  backButton.className = "mode-toggle";
  backButton.textContent = "← Atpakaļ uz bibliotēku";
  backButton.addEventListener("click", () => {
    currentMode = "library";
    localStorage.setItem(MODE_KEY, "library");
    renderMenu();
    renderMainContent();
  });

  modeSection.appendChild(backButton);
  menu.appendChild(modeSection);

  const filterContainer = document.createElement("div");
  filterContainer.className = "filter-container";
  
  const filterLabel = document.createElement("label");
  filterLabel.className = "search-label";
  filterLabel.textContent = "Filtrēt";
  
  const filterSelect = document.createElement("select");
  filterSelect.id = "category-filter";
  filterSelect.className = "form-select";
  
  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = "Visi";
  filterSelect.appendChild(defaultOption);
  
  Object.entries(CATEGORY_FILTERS).forEach(([key, value]) => {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = value;
    filterSelect.appendChild(option);
  });
  
  filterSelect.addEventListener("change", () => {
    renderScenarioList(filterSelect.value);
  });
  
  filterContainer.appendChild(filterLabel);
  filterContainer.appendChild(filterSelect);
  menu.appendChild(filterContainer);

  renderScenarioList();
}

function renderScenarioList(filter = "") {
  const existingList = menu.querySelector(".scenario-list");
  if (existingList) {
    existingList.remove();
  }

  const scenarios = filter ? SCENARIOS.filter(s => s.category === filter) : SCENARIOS;
  
  const list = document.createElement("div");
  list.className = "scenario-list item-list";

  scenarios.forEach(scenario => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "scenario-item audio-item";
    
    const progress = getScenarioProgress(scenario.id);
    if (progress === "confident") {
      button.classList.add("confident");
    } else if (progress === "practiced") {
      button.classList.add("practiced");
    }

    const dot = document.createElement("span");
    dot.className = `progress-dot ${progress}`;
    
    const label = document.createElement("span");
    label.textContent = scenario.title;
    
    const category = document.createElement("small");
    category.textContent = CATEGORY_FILTERS[scenario.category] || scenario.category;
    
    button.append(dot, label, category);
    button.addEventListener("click", () => showScenario(scenario));
    list.appendChild(button);
  });

  menu.appendChild(list);
}

function showScenario(scenario) {
  const reader = document.querySelector(".reader");
  
  const progress = getScenarioProgress(scenario.id);
  
  let checklistHtml = CONFIDENCE_CHECKLIST.map(item => `
    <li>
      <label class="checklist-item">
        <input type="checkbox" data-checklist="${item}" ${progress === "confident" ? "checked" : ""} />
        <span>${item}</span>
      </label>
    </li>
  `).join("");

  let survivalPhrasesHtml = scenario.survivalPhrases.map(phrase => `
    <div class="phrase-card">
      <div class="phrase-lv">${phrase.lv}</div>
      <div class="phrase-en">${phrase.en}</div>
      <div class="phrase-context">${phrase.context}</div>
    </div>
  `).join("");

  let askToRepeatHtml = ASK_TO_REPEAT_PHRASES.map(phrase => `
    <div class="phrase-card practice-card">
      <div class="phrase-lv">${phrase.lv}</div>
      <div class="phrase-en">${phrase.en}</div>
      <div class="phrase-usage">${phrase.usage}</div>
    </div>
  `).join("");

  reader.innerHTML = `
    <section class="scenario-hero">
      <div class="scenario-header">
        <span class="category-badge">${CATEGORY_FILTERS[scenario.category] || scenario.category}</span>
        <h2>${scenario.title}</h2>
        <p class="scenario-subtitle">${scenario.description}</p>
      </div>
      <div class="progress-selector">
        <button class="progress-btn ${progress === 'not_started' ? 'active' : ''}" data-progress="not_started">Nav sākts</button>
        <button class="progress-btn ${progress === 'practiced' ? 'active' : ''}" data-progress="practiced">Nodarbots</button>
        <button class="progress-btn ${progress === 'confident' ? 'active' : ''}" data-progress="confident">Pārliecināts</button>
      </div>
    </section>

    <section class="scenario-section vocabulary-section">
      <h3>🔤 Vārdnīca</h3>
      <div class="vocabulary-list">
        ${scenario.vocabulary.map(word => `<span class="vocab-tag">${word}</span>`).join("")}
      </div>
    </section>

    <section class="scenario-section phrases-section">
      <h3>💬 Frāzes</h3>
      <div class="phrases-grid">
        ${scenario.phrases.map(phrase => `
          <div class="phrase-card">
            <div class="phrase-lv">${phrase.lv}</div>
            <div class="phrase-en">${phrase.en}</div>
            <div class="phrase-context">${phrase.context}</div>
          </div>
        `).join("")}
      </div>
    </section>

    <section class="scenario-section survival-section">
      <h3>🆘 Glābšanas frāzes</h3>
      <div class="phrases-grid">
        ${survivalPhrasesHtml}
      </div>
    </section>

    <section class="scenario-section repeat-section">
      <h3>🔄 Lūdzu atkārtojiet - Mini Practice</h3>
      <p class="section-desc">Practice these essential phrases for asking clarification:</p>
      <div class="phrases-grid repeat-phrases">
        ${askToRepeatHtml}
      </div>
    </section>

    <section class="scenario-section checklist-section">
      <h3>✅ Pārliecības kontrolsaraksts</h3>
      <ul class="checklist">
        ${checklistHtml}
      </ul>
    </section>

    <button class="back-to-scenarios-btn" type="button">← Atpakaļ uz scenārijiem</button>
  `;

  reader.querySelectorAll(".progress-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const newProgress = btn.dataset.progress;
      setScenarioProgress(scenario.id, newProgress);
      showScenario(scenario);
    });
  });

  reader.querySelectorAll(".checklist-item input").forEach(checkbox => {
    checkbox.addEventListener("change", () => {
      const allChecked = Array.from(reader.querySelectorAll(".checklist-item input")).every(cb => cb.checked);
      if (allChecked) {
        setScenarioProgress(scenario.id, "confident");
        showScenario(scenario);
      }
    });
  });

  reader.querySelector(".back-to-scenarios-btn").addEventListener("click", () => {
    renderMainContent();
  });
}

function renderMainContent() {
  const reader = document.querySelector(".reader");
  
  if (currentMode === "living") {
    renderLivingInLatviaMain();
  } else {
    renderLibraryMain();
  }
}

function renderLivingInLatviaMain() {
  const reader = document.querySelector(".reader");
  
  reader.innerHTML = `
    <section class="living-hero hero">
      <div>
        <p class="eyebrow">Praktiskais modulis</p>
        <h2>Dzīvo Latvijā</h2>
        <p>Praktiskās klausīšanās modulis imigrantiem, expātiem, strādājošajiem un ģimenēm.</p>
      </div>
      <span class="badge badge-muted">A2 Level</span>
    </section>

    <section class="living-intro">
      <div class="intro-card">
        <h3>🗂️ Scenāriji</h3>
        <p>Izvēlieties tēmu, kas attiecas uz jūsu ikdienas dzīvi Latvijā. Katrs scenārijs ietver:</p>
        <ul>
          <li>Īsu aprakstu</li>
          <li>Svarīgākos vārdus</li>
          <li>Praktiskas frāzes</li>
          <li>Glābšanas frāzes</li>
          <li>Mini praktika - jautājiet atkārtot</li>
          <li>Pārliecības kontrolsaraksts</li>
        </ul>
      </div>
      <div class="intro-card">
        <h3>📊 Jūsu progress</h3>
        <div class="progress-stats">
          <div class="stat">
            <span class="stat-num">${Object.values(scenarioProgress).filter(p => p !== 'not_started').length}</span>
            <span class="stat-label">Nodarboti</span>
          </div>
          <div class="stat">
            <span class="stat-num">${Object.values(scenarioProgress).filter(p => p === 'confident').length}</span>
            <span class="stat-label">Pārliecināti</span>
          </div>
        </div>
      </div>
    </section>

    <section class="scenario-grid">
      ${SCENARIOS.map(scenario => {
        const progress = getScenarioProgress(scenario.id);
        return `
          <div class="scenario-card ${progress}" data-scenario-id="${scenario.id}">
            <span class="category-tag">${CATEGORY_FILTERS[scenario.category]}</span>
            <h4>${scenario.title}</h4>
            <p>${scenario.description}</p>
            <div class="card-footer">
              <span class="progress-status">
                ${progress === 'confident' ? '✓ Pārliecināts' : progress === 'practiced' ? '◯ Nodarbots' : '○ Nav sākts'}
              </span>
            </div>
          </div>
        `;
      }).join("")}
    </section>
  `;

  reader.querySelectorAll(".scenario-card").forEach(card => {
    card.addEventListener("click", () => {
      const scenario = SCENARIOS.find(s => s.id === card.dataset.scenarioId);
      if (scenario) {
        showScenario(scenario);
      }
    });
  });
}

function renderLibraryMain() {
  const reader = document.querySelector(".reader");
  reader.innerHTML = `
    <section class="hero">
      <div>
        <p class="eyebrow">Latvian listening course</p>
        <h2 id="title">Select an audio item</h2>
        <p id="subtitle">Browse transcripts and translations generated from the MP3 source files.</p>
      </div>
      <span id="statusBadge" class="badge badge-muted">waiting</span>
    </section>

    <section class="player-card">
      <audio id="audio" controls preload="metadata"></audio>
      <div class="nav-buttons">
        <button id="prev" type="button">Previous</button>
        <button id="next" type="button">Next</button>
      </div>
    </section>

    <section class="content-grid">
      <article class="text-panel">
        <div class="panel-heading">
          <h3>Latvian Transcript</h3>
          <a id="lvLink" href="#" target="_blank" rel="noreferrer">Markdown</a>
        </div>
        <pre id="lvText" class="reading-text">No transcript selected.</pre>
      </article>
      <article class="text-panel">
        <div class="panel-heading">
          <h3>English Translation</h3>
          <a id="enLink" href="#" target="_blank" rel="noreferrer">Markdown</a>
        </div>
        <pre id="enText" class="reading-text">No translation selected.</pre>
      </article>
    </section>
  `;
  
  const newAudio = reader.querySelector("#audio");
  const newPrev = reader.querySelector("#prev");
  const newNext = reader.querySelector("#next");
  const newTitle = reader.querySelector("#title");
  const newSubtitle = reader.querySelector("#subtitle");
  const newLvText = reader.querySelector("#lvText");
  const newEnText = reader.querySelector("#enText");
  const newLvLink = reader.querySelector("#lvLink");
  const newEnLink = reader.querySelector("#enLink");
  const newStatusBadge = reader.querySelector("#statusBadge");
  
  const originalAudio = document.querySelector("#audio");
  if (originalAudio) {
    originalAudio.replaceWith(newAudio);
  }
  
  previousButton.replaceWith(newPrev);
  nextButton.replaceWith(newNext);
  title.replaceWith(newTitle);
  subtitle.replaceWith(newSubtitle);
  lvText.replaceWith(newLvText);
  enText.replaceWith(newEnText);
  lvLink.replaceWith(newLvLink);
  enLink.replaceWith(newEnLink);
  statusBadge.replaceWith(newStatusBadge);
  
  window.audioEl = newAudio;
  window.prevBtn = newPrev;
  window.nextBtn = newNext;
  window.titleEl = newTitle;
  window.subtitleEl = newSubtitle;
  window.lvTextEl = newLvText;
  window.enTextEl = newEnText;
  window.lvLinkEl = newLvLink;
  window.enLinkEl = newEnLink;
  window.statusBadgeEl = newStatusBadge;
  
  newPrev.addEventListener("click", () => selectItem(selectedIndex - 1));
  newNext.addEventListener("click", () => selectItem(selectedIndex + 1));
  
  if (filtered.length && selectedIndex >= 0) {
    selectItem(selectedIndex);
  }
}

function selectItem(index) {
  if (index < 0 || index >= filtered.length) return;
  selectedIndex = index;
  const item = filtered[index];
  
  const titleEl = document.querySelector("#title");
  const subtitleEl = document.querySelector("#subtitle");
  const audioEl = document.querySelector("#audio");
  const lvTextEl = document.querySelector("#lvText");
  const enTextEl = document.querySelector("#enText");
  const lvLinkEl = document.querySelector("#lvLink");
  const enLinkEl = document.querySelector("#enLink");
  const statusBadgeEl = document.querySelector("#statusBadge");
  
  setText(titleEl, item.title || item.original_filename, "Untitled audio");
  setText(subtitleEl, `${levelLabels[item.level] || item.level} · ${item.original_filename || ""}`, "");
  audioEl.src = item.audio_url || "";
  setText(lvTextEl, item.lv_text, "Latvian transcript is not available yet.");
  setText(enTextEl, item.en_text, "English translation is not available yet.");
  lvLinkEl.href = item.lv_markdown_url || "#";
  enLinkEl.href = item.en_markdown_url || "#";
  statusBadgeEl.textContent = item.status || "unknown";
  statusBadgeEl.className = badgeClass(item.status);
  
  const prevBtn = document.querySelector("#prev");
  const nextBtn = document.querySelector("#next");
  if (prevBtn) prevBtn.disabled = selectedIndex <= 0;
  if (nextBtn) nextBtn.disabled = selectedIndex >= filtered.length - 1;
  
  renderMenu();
}

function applyFilter() {
  const query = search.value.trim().toLowerCase();
  filtered = catalog.filter((item) => {
    const haystack = [item.title, item.original_filename, item.level, item.status, item.lv_text, item.en_text]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
  selectedIndex = filtered.length ? 0 : -1;
  renderMenu();
  if (filtered.length) {
    selectItem(0);
  } else {
    const titleEl = document.querySelector("#title");
    const subtitleEl = document.querySelector("#subtitle");
    const audioEl = document.querySelector("#audio");
    const lvTextEl = document.querySelector("#lvText");
    const enTextEl = document.querySelector("#enText");
    const statusBadgeEl = document.querySelector("#statusBadge");
    
    setText(titleEl, "No matching audio", "No matching audio");
    setText(subtitleEl, "Try another search or build the catalog after processing files.", "");
    if (audioEl) audioEl.removeAttribute("src");
    setText(lvTextEl, "", "No transcript selected.");
    setText(enTextEl, "", "No translation selected.");
    if (statusBadgeEl) {
      statusBadgeEl.textContent = "empty";
      statusBadgeEl.className = "badge badge-muted";
    }
  }
}

previousButton.addEventListener("click", () => selectItem(selectedIndex - 1));
nextButton.addEventListener("click", () => selectItem(selectedIndex + 1));
search.addEventListener("input", applyFilter);

fetch("catalog.json", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error(`Catalog request failed: ${response.status}`);
    return response.json();
  })
  .then((items) => {
    catalog = Array.isArray(items) ? items : [];
    filtered = catalog.slice();
    renderMenu();
    if (currentMode === "living") {
      renderMainContent();
    } else if (filtered.length) {
      selectItem(0);
    }
  })
  .catch((error) => {
    console.error(error);
    filtered = [];
    renderMenu();
    setText(title, "Catalog not ready", "Catalog not ready");
    setText(subtitle, "Run scripts/build_catalog.py after processing audio.", "");
  });

const brandSection = document.querySelector(".brand");
if (brandSection) {
  const modeButton = document.createElement("button");
  modeButton.type = "button";
  modeButton.className = "mode-switch-btn";
  modeButton.textContent = currentMode === "living" ? "📚 Bibliotēka" : "🏠 Dzīvo Latvijā";
  modeButton.addEventListener("click", () => {
    currentMode = currentMode === "library" ? "living" : "library";
    localStorage.setItem(MODE_KEY, currentMode);
    modeButton.textContent = currentMode === "living" ? "📚 Bibliotēka" : "🏠 Dzīvo Latvijā";
    renderMenu();
    renderMainContent();
  });
  brandSection.appendChild(modeButton);
}