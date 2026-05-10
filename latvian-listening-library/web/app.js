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
const difficultyFilters = document.querySelector("#difficultyFilters");
const audioStyleFilter = document.querySelector("#audioStyleFilter");
const recommendedBtn = document.querySelector("#recommendedBtn");

const levelLabels = {
  A1: "A1 Klausīšanās",
  A2: "A2 Klausīšanās",
};

const difficultyOrder = ["A1+", "Easy A2", "Standard A2", "Fast Native A2"];
const difficultyInfo = {
  "A1+": "Vieglāks par A2 līmeni — ideāls pamats.",
  "Easy A2": "Lēnāka, skaidra ikdienas valoda.",
  "Standard A2": "Paredzamā A2 eksāmena prakse.",
  "Fast Native A2": "Reāls ātrums bet A2 vārdu krājums.",
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

let catalog = [];
let filtered = [];
let selectedIndex = -1;
let currentDifficulty = "all";
let currentAudioStyle = "all";

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
      
      const badges = document.createElement("div");
      badges.className = "item-badges";
      
      if (item.difficulty) {
        const diffBadge = document.createElement("span");
        diffBadge.className = "difficulty-badge";
        diffBadge.textContent = item.difficulty;
        diffBadge.title = difficultyInfo[item.difficulty] || "";
        badges.appendChild(diffBadge);
      }
      
      if (item.audio_style) {
        const styleBadge = document.createElement("span");
        styleBadge.className = "style-badge";
        styleBadge.textContent = item.audio_style;
        badges.appendChild(styleBadge);
      }
      
      const status = document.createElement("small");
      status.textContent = item.status || "unknown";
      button.append(dot, label, badges, status);
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
}

function applyFilter() {
  const query = search.value.trim().toLowerCase();
  filtered = catalog.filter((item) => {
    const haystack = [item.title, item.original_filename, item.level, item.status, item.lv_text, item.en_text]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    if (!haystack.includes(query)) return false;
    if (currentDifficulty !== "all" && item.difficulty !== currentDifficulty) return false;
    if (currentAudioStyle !== "all" && item.audio_style !== currentAudioStyle) return false;
    return true;
  });
  selectedIndex = filtered.length ? 0 : -1;
  renderMenu();
  if (filtered.length) {
    selectItem(0);
  } else {
    setText(title, "No matching audio", "No matching audio");
    setText(subtitle, "Try another search or adjust filters.", "");
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

if (difficultyFilters) {
  difficultyFilters.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    difficultyFilters.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    currentDifficulty = chip.dataset.difficulty || "all";
    applyFilter();
  });
}

if (audioStyleFilter) {
  audioStyleFilter.addEventListener("change", (e) => {
    currentAudioStyle = e.target.value;
    applyFilter();
  });
}

function getRecommendedNext() {
  if (filtered.length === 0) return -1;
  if (selectedIndex < 0) {
    const easyItems = filtered.filter((item) => item.difficulty === "A1+" || item.difficulty === "Easy A2");
    if (easyItems.length > 0) {
      return filtered.findIndex((item) => item.id === easyItems[0].id);
    }
    return 0;
  }
  const currentItem = filtered[selectedIndex];
  const currentDiffIdx = difficultyOrder.indexOf(currentItem.difficulty);
  if (currentDiffIdx === -1) return selectedIndex + 1 < filtered.length ? selectedIndex + 1 : -1;
  const harderItems = filtered.filter((item) => {
    const idx = difficultyOrder.indexOf(item.difficulty);
    return idx > currentDiffIdx;
  });
  if (harderItems.length > 0) {
    return filtered.findIndex((item) => item.id === harderItems[0].id);
  }
  return selectedIndex + 1 < filtered.length ? selectedIndex + 1 : -1;
}

if (recommendedBtn) {
  recommendedBtn.addEventListener("click", () => {
    const recommendedIndex = getRecommendedNext();
    if (recommendedIndex >= 0) {
      selectItem(recommendedIndex);
      recommendedBtn.classList.add("pulse");
      setTimeout(() => recommendedBtn.classList.remove("pulse"), 500);
    }
  });
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
