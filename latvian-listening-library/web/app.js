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
let audioSource = null;
let analyticsInstance = null;
let isDev = window.location.hostname === 'localhost' || window.location.hostname.includes('127.0.0.1');

function badgeClass(status) {
  if (status === "completed") return "badge badge-completed";
  if (status === "transcribed only" || status === "translation failed") return "badge badge-transcribed";
  if (status === "failed") return "badge badge-failed";
  return "badge badge-muted";
}

function setText(node, value, fallback) {
  node.textContent = value && value.trim() ? value : fallback;
}

function initAnalytics() {
  const sinkUrl = isDev ? null : window.ANALYTICS_SINK_URL || null;
  const AnalyticsLib = window.Analytics || {
    EventTypes: {
      AUDIO_PLAY: 'audio_play',
      AUDIO_PAUSE: 'audio_pause',
      SENTENCE_REPLAY: 'sentence_replay',
      LESSON_COMPLETE: 'lesson_complete',
      QUIZ_SUBMIT: 'quiz_submit',
      FLASHCARD_REVIEW: 'flashcard_review',
      EXAM_SIMULATION_COMPLETE: 'exam_simulation_complete',
    }
  };
  
  const sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10);
  analyticsInstance = {
    sessionId,
    events: [],
    track(eventType, payload = {}) {
      const event = {
        id: 'evt_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8),
        type: eventType,
        timestamp: new Date().toISOString(),
        session_id: this.sessionId,
        payload,
      };
      this.events.push(event);
      if (isDev) {
        console.log('[Analytics]', event.type, event.payload);
      }
      if (sinkUrl) {
        fetch(sinkUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(event),
        }).catch(() => {});
      }
    },
    export() {
      return JSON.stringify(this.events, null, 2);
    }
  };
  
  if (audio) {
    audio.addEventListener('play', () => {
      if (filtered[selectedIndex]) {
        analyticsInstance.track(AnalyticsLib.EventTypes.AUDIO_PLAY, {
          lesson_id: filtered[selectedIndex].id,
          filename: filtered[selectedIndex].original_filename,
        });
      }
    });
    
    audio.addEventListener('pause', () => {
      if (filtered[selectedIndex]) {
        analyticsInstance.track(AnalyticsLib.EventTypes.AUDIO_PAUSE, {
          lesson_id: filtered[selectedIndex].id,
          filename: filtered[selectedIndex].original_filename,
        });
      }
    });
  }
}

function validateLesson(lesson) {
  const requiredFields = ['id', 'level', 'original_filename', 'audio_url', 'status'];
  const errors = [];
  
  for (const field of requiredFields) {
    if (!lesson[field]) {
      errors.push(`Missing required field: ${field}`);
    }
  }
  
  if (lesson.level && !['A1', 'A2'].includes(lesson.level)) {
    errors.push(`Invalid level: ${lesson.level}`);
  }
  
  if (isDev && errors.length > 0) {
    console.warn('[LessonValidation]', lesson.id, errors);
  }
  
  return { valid: errors.length === 0, errors };
}

function validateCatalog(items) {
  if (!Array.isArray(items)) {
    return { valid: false, errors: ['Catalog must be an array'], count: 0 };
  }
  
  const invalidLessons = [];
  items.forEach((lesson, index) => {
    const result = validateLesson(lesson);
    if (!result.valid) {
      invalidLessons.push({ index, id: lesson.id, errors: result.errors });
    }
  });
  
  if (isDev && invalidLessons.length > 0) {
    console.warn('[LessonValidation] Invalid lessons:', invalidLessons);
  }
  
  return {
    valid: invalidLessons.length === 0,
    errors: invalidLessons.flatMap(l => l.errors),
    count: items.length,
    invalidCount: invalidLessons.length,
  };
}

function getAudioSource() {
  if (!audioSource) {
    audioSource = {
      getAudioUrl(audioPath) {
        return audioPath;
      },
      getWaveformUrl(audioPath) {
        return audioPath.replace('.mp3', '.waveform.json');
      }
    };
  }
  return audioSource;
}

function renderMenu() {
  menu.textContent = "";
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

function selectItem(index) {
  if (index < 0 || index >= filtered.length) return;
  selectedIndex = index;
  const item = filtered[index];
  const source = getAudioSource();
  
  setText(title, item.title || item.original_filename, "Untitled audio");
  setText(subtitle, `${levelLabels[item.level] || item.level} · ${item.original_filename || ""}`, "");
  
  audio.src = source.getAudioUrl(item.audio_url || "");
  audio.preload = "metadata";
  
  setText(lvText, item.lv_text, "Latvian transcript is not available yet.");
  setText(enText, item.en_text, "English translation is not available yet.");
  lvLink.href = item.lv_markdown_url || "#";
  enLink.href = item.en_markdown_url || "#";
  statusBadge.textContent = item.status || "unknown";
  statusBadge.className = badgeClass(item.status);
  previousButton.disabled = selectedIndex <= 0;
  nextButton.disabled = selectedIndex >= filtered.length - 1;
  
  if (item.waveform_url) {
    fetch(source.getWaveformUrl(item.waveform_url), { cache: "no-store" })
      .then(r => r.ok ? r.json() : null)
      .catch(() => null);
  }
  
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
    setText(title, "No matching audio", "No matching audio");
    setText(subtitle, "Try another search or build the catalog after processing files.", "");
    audio.removeAttribute("src");
    setText(lvText, "", "No transcript selected.");
    setText(enText, "", "No translation selected.");
    statusBadge.textContent = "empty";
    statusBadge.className = "badge badge-muted";
  }
}

previousButton.addEventListener("click", () => selectItem(selectedIndex - 1));
nextButton.addEventListener("click", () => selectItem(selectedIndex + 1));
search.addEventListener("input", applyFilter);

initAnalytics();

fetch("catalog.json", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error(`Catalog request failed: ${response.status}`);
    return response.json();
  })
  .then((items) => {
    const validation = validateCatalog(items);
    catalog = Array.isArray(items) ? items : [];
    if (validation.valid) {
      filtered = catalog.slice();
    } else {
      console.warn('[Catalog] Validation failed, using catalog anyway:', validation.errors);
      filtered = catalog.slice();
    }
    renderMenu();
    if (filtered.length) {
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

window.analytics = analyticsInstance;