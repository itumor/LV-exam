const menu = document.querySelector("#menu");
const search = document.querySelector("#search");
const levelFilter = document.querySelector("#levelFilter");
const styleFilter = document.querySelector("#styleFilter");
const title = document.querySelector("#title");
const subtitle = document.querySelector("#subtitle");
const speakerBadge = document.querySelector("#speakerBadge");
const audio = document.querySelector("#audio");
const lvText = document.querySelector("#lvText");
const enText = document.querySelector("#enText");
const lvLink = document.querySelector("#lvLink");
const enLink = document.querySelector("#enLink");
const statusBadge = document.querySelector("#statusBadge");
const previousButton = document.querySelector("#prev");
const nextButton = document.querySelector("#next");
const voiceRecommendation = document.querySelector("#voiceRecommendation");

const voiceTypes = [
  "cashier",
  "doctor",
  "teacher",
  "colleague",
  "driver",
  "grandmother",
  "grandfather",
  "government",
  "friend",
  "landlord",
];

const speakingStyles = [
  "clear",
  "slow",
  "normal",
  "casual",
  "announcement",
  "dialogue",
];

const voiceTypeLabels = {
  cashier: "Cashier",
  doctor: "Doctor",
  teacher: "Teacher",
  colleague: "Colleague",
  driver: "Bus Driver",
  grandmother: "Grandmother",
  grandfather: "Grandfather",
  government: "Government Office",
  friend: "Friend",
  landlord: "Landlord",
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

function displaySpeakerBadge(item) {
  if (!item || !item.has_speaker) {
    speakerBadge.style.display = "none";
    return;
  }
  const label = item.speaker_label || voiceTypeLabels[item.voice_type] || item.voice_type;
  if (label) {
    speakerBadge.textContent = label;
    speakerBadge.style.display = "inline-block";
  } else {
    speakerBadge.style.display = "none";
  }
}

function getRandomVoiceType(items) {
  const withVoices = items.filter((i) => i.has_speaker && i.voice_type);
  if (withVoices.length === 0) return null;
  const randomIndex = Math.floor(Math.random() * withVoices.length);
  return withVoices[randomIndex].voice_type;
}

function getVoiceRecommendation(currentItem, items) {
  if (!currentItem || !currentItem.has_speaker || !currentItem.voice_type) {
    return "";
  }
  const otherTypes = items.filter(
    (i) => i.has_speaker && i.voice_type && i.voice_type !== currentItem.voice_type
  );
  if (otherTypes.length === 0) {
    return "";
  }
  const nextType = otherTypes[Math.floor(Math.random() * otherTypes.length)].voice_type;
  const label = voiceTypeLabels[nextType] || nextType;
  return `Try a ${label} voice next.`;
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
  displaySpeakerBadge(item);
  audio.src = item.audio_url || "";
  setText(lvText, item.lv_text, "Latvian transcript is not available yet.");
  setText(enText, item.en_text, "English translation is not available yet.");
  lvLink.href = item.lv_markdown_url || "#";
  enLink.href = item.en_markdown_url || "#";
  statusBadge.textContent = item.status || "unknown";
  statusBadge.className = badgeClass(item.status);
  previousButton.disabled = selectedIndex <= 0;
  nextButton.disabled = selectedIndex >= filtered.length - 1;
  setText(voiceRecommendation, getVoiceRecommendation(item, catalog), "");
  renderMenu();
}

function applyFilter() {
  const query = search.value.trim().toLowerCase();
  const styleValue = styleFilter ? styleFilter.value : "";
  filtered = catalog.filter((item) => {
    const haystack = [item.title, item.original_filename, item.level, item.status, item.lv_text, item.en_text]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    if (styleValue && item.speaking_style !== styleValue) {
      return false;
    }
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
    speakerBadge.style.display = "none";
    setText(voiceRecommendation, "", "");
  }
}

previousButton.addEventListener("click", () => selectItem(selectedIndex - 1));
nextButton.addEventListener("click", () => selectItem(selectedIndex + 1));
search.addEventListener("input", applyFilter);
if (styleFilter) {
  styleFilter.addEventListener("change", applyFilter);
}

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
