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
const recommendationsSection = document.querySelector("#recommendations");
const recList = document.querySelector("#recList");
const weakSkills = document.querySelector("#weakSkills");
const resetProgress = document.querySelector("#resetProgress");

const STORAGE_KEY = "latvianListeningProgress";

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
  setText(title, item.title || item.original_filename, "Untitled audio");
  setText(subtitle, `${levelLabels[item.level] || item.level} · ${item.original_filename || ""}`, "");
  audio.src = item.audio_url || "";
  setText(lvText, item.lv_text, "Latvian transcript is not available yet.");
  setText(enText, item.en_text, "English translation is not available yet.");
  lvLink.href = item.lv_markdown_url || "#";
  enLink.href = item.en_markdown_url || "#";
  statusBadge.textContent = item.status || "unknown";
  statusBadge.className = badgeClass(item.status);
  previousButton.disabled = selectedIndex <= 0;
  nextButton.disabled = selectedIndex >= filtered.length - 1;
  renderMenu();
  trackEvent("lesson_opened");
  updateRecommendations();
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

fetch("catalog.json", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error(`Catalog request failed: ${response.status}`);
    return response.json();
  })
  .then((items) => {
    catalog = Array.isArray(items) ? items : [];
    filtered = catalog.slice();
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

audio.addEventListener("play", () => trackEvent("audio_played"));
audio.addEventListener("ended", () => trackEvent("audio_completed"));
audio.addEventListener("seeking", () => {
  if (audio.currentTime > 0 && audio.currentTime < 3) {
    trackEvent("sentence_replayed");
  }
});

let lastSpeed = 1;
audio.addEventListener("ratechange", () => {
  trackEvent("playback_speed_changed", { speed: audio.playbackRate });
  lastSpeed = audio.playbackRate;
});

const transcriptToggle = document.querySelector(".text-panel");
if (transcriptToggle) {
  transcriptToggle.addEventListener("click", () => {
    trackEvent("transcript_toggled");
  });
}

function getStoredProgress() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : { events: [], quizResults: [], flashcardMisses: [], skills: {} };
  } catch {
    return { events: [], quizResults: [], flashcardMisses: [], skills: {} };
  }
}

function saveProgress(progress) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
  } catch (e) {
    console.warn("Could not save progress:", e);
  }
}

function trackEvent(type, data = {}) {
  const progress = getStoredProgress();
  const item = filtered[selectedIndex];
  const event = {
    type,
    itemId: item?.id,
    itemTitle: item?.title,
    itemLevel: item?.level,
    timestamp: Date.now(),
    ...data,
  };
  progress.events.push(event);
  if (progress.events.length > 500) {
    progress.events = progress.events.slice(-500);
  }
  saveProgress(progress);
  updateRecommendations();
}

function recordQuizAnswer(correct, category) {
  const progress = getStoredProgress();
  progress.quizResults.push({ correct, category, timestamp: Date.now() });
  if (progress.quizResults.length > 200) {
    progress.quizResults = progress.quizResults.slice(-200);
  }
  saveProgress(progress);
  updateRecommendations();
}

function recordFlashcardMiss(word) {
  const progress = getStoredProgress();
  progress.flashcardMisses.push({ word, timestamp: Date.now() });
  if (progress.flashcardMisses.length > 300) {
    progress.flashcardMisses = progress.flashcardMisses.slice(-300);
  }
  saveProgress(progress);
  updateRecommendations();
}

function analyzeWeakSkills(progress) {
  const skills = {
    listening: { attempts: 0, correct: 0 },
    numbers: { attempts: 0, correct: 0 },
    directions: { attempts: 0, correct: 0 },
    vocabulary: { attempts: 0, correct: 0 },
  };

  const timeDatePattern = /\d{1,2}[:.]\d{2}|pirmdien|otrdien|trešdien|ceturdien|piektdien|sestdien|svētdien|janvāris|februāris|marts|aprīlis|maijs|jūnijs|jūlijs|augusts|septembris|oktobris|novembris|decembris/;
  const directionPattern = /kreisā|labā|tālāk|pirmais|otrais|trešais|ielā|namā|uzraudzīt/;
  const vocabPattern = /(maize|ūdens|mašīna|māja|cepts|dārzs|lauks)/;

  for (const event of progress.events) {
    if (event.type === "audio_completed" || event.type === "audio_played") {
      skills.listening.attempts++;
      if (event.type === "audio_completed") {
        skills.listening.correct++;
      }
      if (event.itemTitle && timeDatePattern.test(event.itemTitle)) {
        skills.numbers.attempts++;
      }
      if (event.itemTitle && directionPattern.test(event.itemTitle)) {
        skills.directions.attempts++;
      }
      if (event.itemTitle && vocabPattern.test(event.itemTitle)) {
        skills.vocabulary.attempts++;
      }
    }
  }

  for (const miss of progress.flashcardMisses) {
    skills.vocabulary.attempts++;
  }

  for (const quiz of progress.quizResults) {
    if (quiz.category && skills[quiz.category]) {
      skills[quiz.category].attempts++;
      if (quiz.correct) {
        skills[quiz.category].correct++;
      }
    }
  }

  return skills;
}

function getRecommendations(progress) {
  const recommendations = [];
  const skills = analyzeWeakSkills(progress);
  const recentEvents = progress.events.slice(-50);
  const slowPlaybackCount = recentEvents.filter((e) => e.speed && e.speed < 1).length;
  const replays = recentEvents.filter((e) => e.type === "sentence_replayed").length;

  const completedIds = new Set(
    progress.events
      .filter((e) => e.type === "audio_completed")
      .map((e) => e.itemId)
      .filter(Boolean)
  );

  const recentQuizzes = progress.quizResults.slice(-10);
  const recentCorrect = recentQuizzes.filter((q) => q.correct).length;
  if (recentQuizzes.length >= 3 && recentCorrect / recentQuizzes.length < 0.5) {
    const lowerLevel = "A1";
    const easierItems = filtered.filter(
      (item) =>
        item.level === lowerLevel &&
        !completedIds.has(item.id) &&
        !recentEvents.find((e) => e.itemId === item.id)
    );
    if (easierItems.length > 0) {
      recommendations.push({
        item: easierItems[0],
        reason: "Practice at an easier level to build confidence.",
      });
    }
  }

  for (const [skill, data] of Object.entries(skills)) {
    if (data.attempts >= 3) {
      const accuracy = data.correct / data.attempts;
      if (accuracy < 0.6) {
        const targetItems = filtered.filter(
          (item) =>
            (item.level === "A1" ||
              (item.title && item.title.toLowerCase().includes(skill))) &&
            !completedIds.has(item.id)
        );
        if (targetItems.length > 0) {
          recommendations.push({
            item: targetItems[0],
            reason: `You struggle with ${skill}. Practice these foundations.`,
          });
          break;
        }
      }
    }
  }

  if (progress.flashcardMisses.length >= 5) {
    const vocabItems = filtered.filter(
      (item) =>
        item.level === "A1" && !completedIds.has(item.id) && item.status === "completed"
    );
    if (vocabItems.length > 0) {
      recommendations.push({
        item: vocabItems[0],
        reason: "Review vocabulary you missed recently.",
      });
    }
  }

  if (slowPlaybackCount >= 3 || replays >= 5) {
    const slowItems = filtered.filter(
      (item) =>
        item.level === "A1" && item.status === "completed" && !completedIds.has(item.id)
    );
    if (slowItems.length > 0) {
      recommendations.push({
        item: slowItems[0],
        reason: "Start with slower audio to reinforce listening skills.",
      });
    }
  }

  const practiceCount = progress.events.filter(
    (e) => e.type === "audio_completed"
  ).length;
  if (practiceCount >= 10 && recentQuizzes.length === 0) {
    const quizItems = filtered.filter(
      (item) => !completedIds.has(item.id) && item.status === "completed"
    );
    if (quizItems.length > 0) {
      recommendations.push({
        item: quizItems[0],
        reason: "You've practiced enough. Try the exam simulation now!",
      });
    }
  }

  const untouched = filtered.filter(
    (item) =>
      (!completedIds.has(item.id) ||
        !recentEvents.find((e) => e.itemId === item.id)) &&
      item.status === "completed"
  );
  for (const item of untouched.slice(0, 3 - recommendations.length)) {
    if (!recommendations.find((r) => r.item.id === item.id)) {
      recommendations.push({
        item,
        reason: "Continue with more listening practice.",
      });
    }
  }

  return recommendations.slice(0, 3);
}

function updateRecommendations() {
  const progress = getStoredProgress();
  if (progress.events.length === 0) {
    recommendationsSection.hidden = true;
    return;
  }
  recommendationsSection.hidden = false;

  const recommendations = getRecommendations(progress);
  recList.innerHTML = "";
  for (const rec of recommendations) {
    const el = document.createElement("div");
    el.className = "rec-item";
    el.innerHTML = `
      <div class="rec-item-content">
        <span class="rec-item-title">${rec.item.title || rec.item.original_filename}</span>
        <span class="rec-item-reason">${rec.reason}</span>
      </div>
      <button type="button" class="rec-item-btn">Start</button>
    `;
    el.querySelector(".rec-item-btn").addEventListener("click", () => {
      const idx = filtered.findIndex((i) => i.id === rec.item.id);
      if (idx >= 0) {
        selectItem(idx);
      }
    });
    recList.appendChild(el);
  }

  const skills = analyzeWeakSkills(progress);
  weakSkills.innerHTML = "";
  const skillNames = {
    listening: "Listening Comprehension",
    numbers: "Numbers & Dates",
    directions: "Directions & Places",
    vocabulary: "Vocabulary Retention",
  };
  for (const [key, data] of Object.entries(skills)) {
    if (data.attempts > 0) {
      const accuracy = Math.round((data.correct / data.attempts) * 100);
      const el = document.createElement("div");
      el.className = "weak-skill-item";
      el.innerHTML = `
        <span class="weak-skill-name">${skillNames[key]}</span>
        <div class="weak-skill-bar">
          <div class="weak-skill-fill" style="width: ${accuracy}%"></div>
        </div>
      `;
      weakSkills.appendChild(el);
    }
  }
  if (!weakSkills.innerHTML) {
    weakSkills.innerHTML = "<p>Complete lessons to see skill insights.</p>";
  }
}

resetProgress.addEventListener("click", () => {
  if (confirm("Reset all local learning progress? This cannot be undone.")) {
    localStorage.removeItem(STORAGE_KEY);
    recommendationsSection.hidden = true;
  }
});

document.addEventListener("DOMContentLoaded", updateRecommendations);
