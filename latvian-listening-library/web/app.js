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
const themeToggle = document.querySelector("#themeToggle");
const themeIcon = document.querySelector("#themeIcon");
const waveform = document.querySelector("#waveform");
const statsRow = document.querySelector("#statsRow");
const progressFill = document.querySelector("#progressFill");
const completedCount = document.querySelector("#completedCount");
const streakCount = document.querySelector("#streakCount");
const heroSection = document.querySelector("#heroSection");
const emptyState = document.querySelector("#emptyState");

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

function initTheme() {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const stored = localStorage.getItem("theme");
  if (stored === "dark" || (!stored && prefersDark)) {
    document.body.classList.add("dark");
    themeIcon.innerHTML = "&#9728;";
  } else {
    themeIcon.innerHTML = "&#9790;";
  }
}

function toggleTheme() {
  const isDark = document.body.classList.toggle("dark");
  localStorage.setItem("theme", isDark ? "dark" : "light");
  themeIcon.innerHTML = isDark ? "&#9728;" : "&#9790;";
}

themeToggle?.addEventListener("click", toggleTheme);

function badgeClass(status) {
  if (status === "completed") return "badge badge-completed";
  if (status === "transcribed only" || status === "translation failed") return "badge badge-transcribed";
  if (status === "failed") return "badge badge-failed";
  return "badge badge-muted";
}

function setText(node, value, fallback) {
  node.textContent = value && value.trim() ? value : fallback;
}

function showSkeleton(panelId, lines = 4) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  const skeleton = document.createElement("div");
  skeleton.className = "skeleton-container";
  skeleton.innerHTML = `
    <div class="skeleton skeleton-title"></div>
    ${Array(lines).fill('<div class="skeleton skeleton-text"></div>').join("")}
    <div class="skeleton skeleton-text" style="width: 60%"></div>
  `;
  panel.innerHTML = "";
  panel.appendChild(skeleton);
}

function initWaveform() {
  waveform.innerHTML = "";
  const bars = 60;
  for (let i = 0; i < bars; i++) {
    const bar = document.createElement("div");
    bar.className = "waveform-bar";
    bar.style.height = `${20 + Math.random() * 60}%`;
    waveform.appendChild(bar);
  }
}

function updateWaveform(progress) {
  const bars = waveform.querySelectorAll(".waveform-bar");
  const activeIndex = Math.floor(progress * bars.length);
  bars.forEach((bar, i) => {
    bar.classList.toggle("active", i <= activeIndex);
  });
}

function showLoading() {
  showSkeleton("lvTextPanel", 5);
  showSkeleton("enTextPanel", 5);
}

function showContent() {
  const lvPanel = document.getElementById("lvTextPanel");
  const enPanel = document.getElementById("enTextPanel");
  if (lvPanel) lvPanel.innerHTML = `<pre id="lvText" class="reading-text">${lvText.textContent}</pre>`;
  if (enPanel) enPanel.innerHTML = `<pre id="enText" class="reading-text">${enText.textContent}</pre>`;
}

function updateProgress() {
  const completed = catalog.filter(i => i.status === "completed").length;
  const total = catalog.length;
  const percent = total ? Math.round((completed / total) * 100) : 0;
  progressFill.style.width = `${percent}%`;
  progressFill.parentElement.setAttribute("aria-valuenow", percent);
  completedCount.textContent = completed;
  const streak = parseInt(localStorage.getItem("streak") || "0", 10);
  const lastDate = localStorage.getItem("lastVisit");
  const today = new Date().toDateString();
  if (lastDate !== today) {
    const yesterday = new Date(Date.now() - 86400000).toDateString();
    const newStreak = lastDate === yesterday ? streak + 1 : 1;
    localStorage.setItem("streak", newStreak);
    localStorage.setItem("lastVisit", today);
    streakCount.textContent = newStreak;
  } else {
    streakCount.textContent = streak;
  }
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
    const icon = document.createElement("span");
    icon.className = "level-toggle-icon";
    icon.textContent = "−";
    toggle.appendChild(icon);

    const list = document.createElement("div");
    list.className = "item-list";

    for (const item of items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "audio-item";
      if (filtered[selectedIndex] && filtered[selectedIndex].id === item.id) {
        button.classList.add("active");
      }
      button.setAttribute("aria-label", `Play ${item.title || item.original_filename}`);
      button.addEventListener("click", () => selectItem(filtered.findIndex((candidate) => candidate.id === item.id)));

      const dot = document.createElement("span");
      dot.className = "play-dot";
      const label = document.createElement("span");
      label.className = "audio-item-label";
      label.textContent = item.title || item.original_filename || "Audio";
      const status = document.createElement("small");
      status.className = "audio-item-status";
      status.textContent = item.status || "unknown";
      button.append(dot, label, status);
      list.appendChild(button);
    }

    toggle.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!expanded));
      icon.textContent = expanded ? "+" : "−";
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
  
  heroSection?.removeAttribute("hidden");
  emptyState?.setAttribute("hidden", "");
  showContent();
  initWaveform();
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
    statusBadge.textContent = "empty";
    statusBadge.className = "badge badge-muted";
  }
}

previousButton.addEventListener("click", () => selectItem(selectedIndex - 1));
nextButton.addEventListener("click", () => selectItem(selectedIndex + 1));
search.addEventListener("input", applyFilter);

audio.addEventListener("timeupdate", () => {
  const progress = audio.duration ? audio.currentTime / audio.duration : 0;
  updateWaveform(progress);
  const progressBar = progressFill?.parentElement;
  if (progressBar) {
    progressBar.setAttribute("aria-valuenow", Math.round(progress * 100));
  }
});

audio.addEventListener("loadedmetadata", () => {
  initWaveform();
});

initTheme();
initWaveform();

fetch("catalog.json", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error(`Catalog request failed: ${response.status}`);
    return response.json();
  })
  .then((items) => {
    catalog = Array.isArray(items) ? items : [];
    filtered = catalog.slice();
    renderMenu();
    statsRow?.removeAttribute("hidden");
    updateProgress();
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