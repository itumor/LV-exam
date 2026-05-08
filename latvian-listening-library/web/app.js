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

const compBarFill = document.querySelector("#compBarFill");
const compPct = document.querySelector("#compPct");
const compLabel = document.querySelector("#compLabel");
const compEstimateNote = document.querySelector("#compEstimateNote");
const compMeterCard = document.querySelector("#compMeterCard");
const statTotal = document.querySelector("#statTotal");
const statUnique = document.querySelector("#statUnique");
const statUnknown = document.querySelector("#statUnknown");
const unknownWordList = document.querySelector("#unknownWordList");

let activeCompFilter = "all";

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

function renderComprehensionMeter(lvText) {
  if (!lvText || !lvText.trim()) {
    compMeterCard.hidden = true;
    return;
  }
  compMeterCard.hidden = false;

  const stats = ComprehensionMeter.computeLessonStats(lvText);
  const { label, key } = ComprehensionMeter.getComprehensionLabel(stats.comprehensionPct);

  compBarFill.style.width = stats.comprehensionPct + "%";
  compBarFill.className = "comp-bar-fill comp-bar-" + key;
  compPct.textContent = "You may understand ~" + stats.comprehensionPct + "%";
  compLabel.textContent = label;
  compLabel.className = "comp-label comp-label-" + key;

  compEstimateNote.textContent = stats.isEstimate
    ? "Rough estimate — no vocabulary saved yet"
    : "Estimate based on your saved words";

  statTotal.textContent = stats.totalWords;
  statUnique.textContent = stats.uniqueWords;
  statUnknown.textContent = stats.unknownUniqueWords + " unknown";

  unknownWordList.innerHTML = "";
  if (stats.topUnknownWords.length === 0) {
    const empty = document.createElement("p");
    empty.className = "unknown-empty";
    empty.textContent = "Great — no unknown words detected!";
    unknownWordList.appendChild(empty);
  } else {
    for (const { word, count } of stats.topUnknownWords) {
      const tag = document.createElement("button");
      tag.type = "button";
      tag.className = "unknown-word-tag";
      tag.textContent = word + (count > 1 ? " (" + count + ")" : "");
      tag.addEventListener("click", () => {
        ComprehensionMeter.saveKnownWord(word, "manual");
        renderComprehensionMeter(lvText);
        reapplyFilters();
      });
      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "unknown-word-remove";
      removeBtn.textContent = "✓";
      removeBtn.title = "Mark as known";
      removeBtn.addEventListener("click", () => {
        ComprehensionMeter.saveKnownWord(word, "manual");
        renderComprehensionMeter(lvText);
        reapplyFilters();
      });
      const wrap = document.createElement("span");
      wrap.className = "unknown-word-wrap";
      wrap.appendChild(tag);
      wrap.appendChild(removeBtn);
      unknownWordList.appendChild(wrap);
    }
  }
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
  renderComprehensionMeter(item.lv_text);
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

function reapplyFilters() {
  if (activeCompFilter === "all") {
    if (search.value.trim()) {
      applyFilter();
    } else {
      filtered = catalog.slice();
      selectedIndex = filtered.length ? 0 : -1;
      renderMenu();
      if (filtered.length) selectItem(0);
    }
  } else {
    const query = search.value.trim().toLowerCase();
    filtered = catalog.filter((item) => {
      const matchesQuery = !query || [item.title, item.original_filename, item.level, item.status, item.lv_text, item.en_text]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query);
      if (!matchesQuery) return false;
      if (activeCompFilter === "all") return true;
      const filtered2 = ComprehensionMeter.filterCatalogByLabel([item], activeCompFilter);
      return filtered2.length > 0;
    });
    selectedIndex = filtered.length ? 0 : -1;
    renderMenu();
    if (filtered.length) selectItem(0);
  }
}

document.querySelectorAll(".comp-filter-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".comp-filter-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    activeCompFilter = btn.dataset.filter;
    if (activeCompFilter === "all") {
      filtered = catalog.slice();
      if (search.value.trim()) {
        applyFilter();
      } else {
        selectedIndex = filtered.length ? 0 : -1;
        renderMenu();
        if (filtered.length) selectItem(0);
      }
    } else {
      const query = search.value.trim().toLowerCase();
      filtered = catalog.filter((item) => {
        const matchesQuery = !query || [item.title, item.original_filename, item.level, item.status, item.lv_text, item.en_text]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(query);
        if (!matchesQuery) return false;
        const filtered2 = ComprehensionMeter.filterCatalogByLabel([item], activeCompFilter);
        return filtered2.length > 0;
      });
      selectedIndex = filtered.length ? 0 : -1;
      renderMenu();
      if (filtered.length) selectItem(0);
    }
  });
});
