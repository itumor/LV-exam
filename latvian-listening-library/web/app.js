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

// Theme management
function initTheme() {
  const saved = localStorage.getItem("theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  if (saved === "dark" || (!saved && prefersDark)) {
    document.body.classList.add("dark");
  }
}

function toggleTheme() {
  document.body.classList.toggle("dark");
  const isDark = document.body.classList.contains("dark");
  localStorage.setItem("theme", isDark ? "dark" : "light");
}

// Progress tracking
function getProgress() {
  const stored = localStorage.getItem("listeningProgress");
  return stored ? JSON.parse(stored) : { completed: 0, total: 0, streak: 0, xp: 0, lastDate: null };
}

function updateProgress() {
  const progress = getProgress();
  const today = new Date().toDateString();
  if (progress.lastDate !== today) {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    if (progress.lastDate === yesterday.toDateString()) {
      progress.streak += 1;
    } else {
      progress.streak = 1;
    }
  }
  progress.xp += 10;
  progress.lastDate = today;
  localStorage.setItem("listeningProgress", JSON.stringify(progress));
  renderProgress();
}

function renderProgress() {
  const progress = getProgress();
  const progressBar = document.getElementById("progressBar");
  const progressText = document.getElementById("progressText");
  const streakEl = document.getElementById("streakCount");
  const xpEl = document.getElementById("xpCount");
  
  if (progressBar) {
    const pct = progress.total > 0 ? (progress.completed / progress.total) * 100 : 0;
    progressBar.style.width = `${pct}%`;
  }
  if (progressText) progressText.textContent = `${progress.completed}/${progress.total}`;
  if (streakEl) streakEl.textContent = progress.streak;
  if (xpEl) xpEl.textContent = progress.xp;
}

// Waveform visualization
function initWaveform() {
  const container = document.getElementById("waveform");
  if (!container) return;
  
  const canvas = document.createElement("canvas");
  canvas.width = container.clientWidth || 400;
  canvas.height = 60;
  container.appendChild(canvas);
  
  const ctx = canvas.getContext("2d");
  const barWidth = 3;
  const gap = 2;
  const bars = Math.floor(canvas.width / (barWidth + gap));
  
  // Generate mock waveform data if none available
  const waveformData = Array.from({ length: bars }, () => Math.random() * 0.7 + 0.1);
  
  function draw(progress = 0) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const progressX = progress * canvas.width;
    
    waveformData.forEach((height, i) => {
      const x = i * (barWidth + gap);
      const y = (canvas.height - height * canvas.height) / 2;
      ctx.fillStyle = x <= progressX ? "#d60a4f" : "#d6e1e7";
      ctx.fillRect(x, y, barWidth, height * canvas.height);
    });
  }
  
  audio.addEventListener("timeupdate", () => {
    if (audio.duration) draw(audio.currentTime / audio.duration);
  });
  
  audio.addEventListener("loadedmetadata", () => draw(0));
  
  container.waveformDraw = draw;
}

// Skeleton loading
function setLoading(loading) {
  const lvPanel = lvText.parentElement;
  const enPanel = enText.parentElement;
  
  if (loading) {
    lvPanel.classList.add("skeleton");
    enPanel.classList.add("skeleton");
    lvText.textContent = "";
    enText.textContent = "";
  } else {
    lvPanel.classList.remove("skeleton");
    enPanel.classList.remove("skeleton");
  }
}

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
  
  setLoading(true);
  setText(title, item.title || item.original_filename, "Untitled audio");
  setText(subtitle, `${levelLabels[item.level] || item.level} · ${item.original_filename || ""}`, "");
  audio.src = item.audio_url || "";
  
  setTimeout(() => {
    setText(lvText, item.lv_text, "Latvian transcript is not available yet.");
    setText(enText, item.en_text, "English translation is not available yet.");
    setLoading(false);
    updateProgress();
    
    // Update waveform if available
    const waveformContainer = document.getElementById("waveform");
    if (waveformContainer && waveformContainer.waveformDraw) {
      waveformContainer.waveformDraw(0);
    }
  }, 300);
  
  lvLink.href = item.lv_markdown_url || "#";
  enLink.href = item.en_markdown_url || "#";
  statusBadge.textContent = item.status || "unknown";
  statusBadge.className = badgeClass(item.status);
  previousButton.disabled = selectedIndex <= 0;
  nextButton.disabled = selectedIndex >= filtered.length - 1;
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

// Initialize theme toggle
document.getElementById("themeToggle").addEventListener("click", toggleTheme);

// Initialize on load
initTheme();
renderProgress();
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
