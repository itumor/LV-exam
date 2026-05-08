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
const sidebar = document.querySelector("#sidebar");
const sidebarToggle = document.querySelector("#sidebarToggle");
const menuTrigger = document.querySelector("#menuTrigger");
const stickyPlayer = document.querySelector("#stickyPlayer");
const stickyPlayBtn = document.querySelector("#stickyPlayBtn");
const stickyTitle = document.querySelector("#stickyTitle");
const stickyProgress = document.querySelector("#stickyProgress");
const stickyTime = document.querySelector("#stickyTime");
const stickySpeedBtn = document.querySelector("#stickySpeedBtn");
const stickyReplayBtn = document.querySelector("#stickyReplayBtn");
const lvCollapse = document.querySelector("#lvCollapse");
const enCollapse = document.querySelector("#enCollapse");
const offlineIndicator = document.querySelector("#offlineIndicator");
const installPrompt = document.querySelector("#installPrompt");
const installDismiss = document.querySelector("#installDismiss");
const installAction = document.querySelector("#installAction");

const playIcon = stickyPlayBtn.querySelector(".play-icon");
const pauseIcon = stickyPlayBtn.querySelector(".pause-icon");

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
  "Ikdienas darki",
  "Iepirkšanās",
  "Labu apetīti!",
  "Brīvais laiks",
  "Es ceļoju",
  "Esi vesels!",
  "Mācības un darbs",
];

const speedOptions = [0.5, 0.75, 1, 1.25, 1.5, 2];
let currentSpeedIndex = 2;

let catalog = [];
let filtered = [];
let selectedIndex = -1;
let deferredPrompt = null;

function badgeClass(status) {
  if (status === "completed") return "badge badge-completed";
  if (status === "transcribed only" || status === "translation failed") return "badge badge-transcribed";
  if (status === "failed") return "badge badge-failed";
  return "badge badge-muted";
}

function setText(node, value, fallback) {
  node.textContent = value && value.trim() ? value : fallback;
}

function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function togglePlayPause() {
  if (audio.paused) {
    audio.play();
  } else {
    audio.pause();
  }
}

function updateStickyPlayerUI(playing) {
  if (playing) {
    playIcon.style.display = "none";
    pauseIcon.style.display = "block";
  } else {
    playIcon.style.display = "block";
    pauseIcon.style.display = "none";
  }
}

function updateMediaSession(playing) {
  if (!("mediaSession" in navigator)) return;
  const item = filtered[selectedIndex];
  if (!item) return;
  
  navigator.mediaSession.setActionHandler("play", () => { audio.play(); });
  navigator.mediaSession.setActionHandler("pause", () => { audio.pause(); });
  navigator.mediaSession.setActionHandler("seekbackward", () => {
    audio.currentTime = Math.max(0, audio.currentTime - 10);
  });
  navigator.mediaSession.setActionHandler("seekforward", () => {
    audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 10);
  });
  
  if (selectedIndex > 0) {
    navigator.mediaSession.setActionHandler("previoustrack", () => selectItem(selectedIndex - 1));
  }
  if (selectedIndex < filtered.length - 1) {
    navigator.mediaSession.setActionHandler("nexttrack", () => selectItem(selectedIndex + 1));
  }
  
  const artwork = [];
  if (item.artwork_url) {
    artwork.push({ src: item.artwork_url, sizes: "512x512", type: "image/png" });
  }
  
  navigator.mediaSession.metadata = new MediaMetadata({
    title: item.title || item.original_filename || "Audio",
    artist: "Latvian Listening Library",
    album: levelLabels[item.level] || item.level,
    artwork: artwork,
  });
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
      button.addEventListener("click", () => {
        selectItem(filtered.findIndex((candidate) => candidate.id === item.id));
        if (window.innerWidth <= 900) {
          sidebar.classList.remove("open");
        }
      });

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
  
  setText(stickyTitle, item.title || item.original_filename || "Select audio", "Select audio");
  stickyPlayer.classList.remove("hidden");
  
  if (window.innerWidth <= 900) {
    lvText.classList.add("collapsed");
    enText.classList.add("collapsed");
    lvCollapse.textContent = "+";
    enCollapse.textContent = "+";
  }
  
  updateMediaSession(false);
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

function cycleSpeed() {
  currentSpeedIndex = (currentSpeedIndex + 1) % speedOptions.length;
  const speed = speedOptions[currentSpeedIndex];
  audio.playbackRate = speed;
  stickySpeedBtn.textContent = `${speed}×`;
}

function toggleSentenceReplay(event) {
  const target = event.target;
  if (target.tagName === "SPAN" && target.classList.contains("segment")) {
    const start = parseFloat(target.dataset.start);
    const end = parseFloat(target.dataset.end);
    if (!isNaN(start)) {
      audio.currentTime = start;
      audio.play();
    }
  }
}

function setupAudioListeners() {
  audio.addEventListener("play", () => {
    updateStickyPlayerUI(true);
    updateMediaSession(true);
  });
  
  audio.addEventListener("pause", () => {
    updateStickyPlayerUI(false);
    updateMediaSession(false);
  });
  
  audio.addEventListener("ended", () => {
    updateStickyPlayerUI(false);
    updateMediaSession(false);
  });
  
  audio.addEventListener("timeupdate", () => {
    const progress = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
    stickyProgress.value = progress;
    const current = formatTime(audio.currentTime);
    const total = formatTime(audio.duration);
    stickyTime.textContent = `${current} / ${total}`;
  });
  
  audio.addEventListener("loadedmetadata", () => {
    stickyProgress.value = 0;
    stickyTime.textContent = `0:00 / ${formatTime(audio.duration)}`;
  });
  
  stickyProgress.addEventListener("input", () => {
    if (audio.duration) {
      audio.currentTime = (stickyProgress.value / 100) * audio.duration;
    }
  });
  
  stickyPlayBtn.addEventListener("click", togglePlayPause);
  stickySpeedBtn.addEventListener("click", cycleSpeed);
  
  stickyReplayBtn.addEventListener("click", () => {
    audio.currentTime = Math.max(0, audio.currentTime - 10);
  });
}

function setupMobileUI() {
  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", () => {
      sidebar.classList.remove("open");
    });
  }
  
  if (menuTrigger) {
    menuTrigger.addEventListener("click", () => {
      sidebar.classList.add("open");
    });
  }
  
  if (lvCollapse) {
    lvCollapse.addEventListener("click", () => {
      const collapsed = lvText.classList.toggle("collapsed");
      lvCollapse.textContent = collapsed ? "+" : "−";
    });
  }
  
  if (enCollapse) {
    enCollapse.addEventListener("click", () => {
      const collapsed = enText.classList.toggle("collapsed");
      enCollapse.textContent = collapsed ? "+" : "−";
    });
  }
}

function setupPWA() {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    const stored = localStorage.getItem("installDismissed");
    if (!stored || Date.now() - parseInt(stored) > 86400000) {
      installPrompt.style.display = "block";
    }
  });
  
  if (installDismiss) {
    installDismiss.addEventListener("click", () => {
      installPrompt.style.display = "none";
      localStorage.setItem("installDismissed", Date.now().toString());
    });
  }
  
  if (installAction) {
    installAction.addEventListener("click", async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === "accepted") {
        installPrompt.style.display = "none";
      }
      deferredPrompt = null;
    });
  }
  
  window.addEventListener("appinstalled", () => {
    installPrompt.style.display = "none";
    deferredPrompt = null;
  });
}

function setupMediaSession() {
  if (!("mediaSession" in navigator)) return;
  
  navigator.mediaSession.setActionHandler("play", () => { audio.play(); });
  navigator.mediaSession.setActionHandler("pause", () => { audio.pause(); });
  navigator.mediaSession.setActionHandler("seekbackward", () => {
    audio.currentTime = Math.max(0, audio.currentTime - 10);
  });
  navigator.mediaSession.setActionHandler("seekforward", () => {
    audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 10);
  });
  navigator.mediaSession.setActionHandler("previoustrack", () => {
    if (selectedIndex > 0) selectItem(selectedIndex - 1);
  });
  navigator.mediaSession.setActionHandler("nexttrack", () => {
    if (selectedIndex < filtered.length - 1) selectItem(selectedIndex + 1);
  });
}

function updateOfflineIndicator() {
  if ("serviceWorker" in navigator && navigator.serviceWorker.controller) {
    navigator.serviceWorker.ready.then(() => {
      if (offlineIndicator) {
        offlineIndicator.style.display = "flex";
      }
    });
  }
}

previousButton.addEventListener("click", () => selectItem(selectedIndex - 1));
nextButton.addEventListener("click", () => selectItem(selectedIndex + 1));
search.addEventListener("input", applyFilter);

setupAudioListeners();
setupMobileUI();
setupPWA();
setupMediaSession();
updateOfflineIndicator();

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

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch((err) => {
    console.warn("SW registration failed:", err);
  });
}