const CommunityService = (function () {
  const STORAGE_KEY = "lv_listening_community";
  const REPORTED_KEY = "lv_listening_reported";

  function getEntries() {
    try {
      const data = localStorage.getItem(STORAGE_KEY);
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  }

  function saveEntries(entries) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  }

  function getReported() {
    try {
      const data = localStorage.getItem(REPORTED_KEY);
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  }

  function saveReported(reported) {
    localStorage.setItem(REPORTED_KEY, JSON.stringify(reported));
  }

  function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substring(2);
  }

  return {
    getEntries: function (lessonId, type, sort) {
      const entries = getEntries().filter(
        (e) => e.lessonId === lessonId && e.type === type
      );
      const reported = getReported();
      const filtered = entries.filter((e) => !reported.includes(e.id));
      if (sort === "helpful") {
        filtered.sort((a, b) => (b.helpfulVotes || 0) - (a.helpfulVotes || 0));
      } else {
        filtered.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
      }
      return filtered;
    },

    addEntry: function (data) {
      const entries = getEntries();
      const entry = {
        id: generateId(),
        lessonId: data.lessonId,
        sentenceId: data.sentenceId || null,
        type: data.type,
        authorDisplayName: data.authorDisplayName,
        body: data.body,
        createdAt: new Date().toISOString(),
        status: "approved",
        helpfulVotes: 0,
        helpfulBy: [],
      };
      entries.push(entry);
      saveEntries(entries);
      return entry;
    },

    voteHelpful: function (entryId) {
      const entries = getEntries();
      const entry = entries.find((e) => e.id === entryId);
      if (entry) {
        entry.helpfulVotes = (entry.helpfulVotes || 0) + 1;
        saveEntries(entries);
        return entry;
      }
      return null;
    },

    report: function (entryId) {
      const reported = getReported();
      if (!reported.includes(entryId)) {
        reported.push(entryId);
        saveReported(reported);
      }
      return true;
    },

    getCount: function (lessonId) {
      const entries = getEntries().filter((e) => e.lessonId === lessonId);
      const reported = getReported();
      return entries.filter((e) => !reported.includes(e.id)).length;
    },

    subscribe: function (callback) {
      window.addEventListener("storage", (e) => {
        if (e.key === STORAGE_KEY || e.key === REPORTED_KEY) {
          callback();
        }
      });
    },
  };
})();

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

(function () {
  const panel = document.getElementById("communityPanel");
  const toggle = document.getElementById("communityToggle");
  const closeBtn = document.getElementById("communityClose");
  const tabs = document.querySelectorAll(".community-tabs .tab");
  const entryType = document.getElementById("entryType");
  const authorName = document.getElementById("authorName");
  const entryBody = document.getElementById("entryBody");
  const submitBtn = document.getElementById("submitEntry");
  const sortOrder = document.getElementById("sortOrder");
  const listEl = document.getElementById("communityList");

  let currentTab = "questions";
  let currentLessonId = null;

  function getLessonId() {
    if (filtered[selectedIndex]) {
      return filtered[selectedIndex].id;
    }
    return "default";
  }

  function getEntryType() {
    const typeMap = {
      questions: "question",
      comments: "comment",
      translations: "translation_suggestion",
    };
    return typeMap[currentTab];
  }

  function renderEntry(entry) {
    const div = document.createElement("div");
    div.className = "community-entry";
    div.dataset.id = entry.id;
    div.innerHTML = `
      <div class="entry-header">
        <span class="entry-type">${entry.type}</span>
        <span class="entry-author">${entry.authorDisplayName}</span>
      </div>
      <div class="entry-body">${entry.body}</div>
      <div class="entry-footer">
        <button type="button" class="helpful-btn">👍 Helpful (${entry.helpfulVotes || 0})</button>
        <button type="button" class="report-btn">🚩 Report</button>
      </div>
    `;
    const helpfulBtn = div.querySelector(".helpful-btn");
    helpfulBtn.addEventListener("click", () => {
      CommunityService.voteHelpful(entry.id);
      renderList();
    });
    const reportBtn = div.querySelector(".report-btn");
    reportBtn.addEventListener("click", () => {
      CommunityService.report(entry.id);
      renderList();
    });
    return div;
  }

  function renderList() {
    listEl.textContent = "";
    currentLessonId = getLessonId();
    const entries = CommunityService.getEntries(
      currentLessonId,
      getEntryType(),
      sortOrder.value
    );
    if (entries.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const emptyMessages = {
        questions: "No questions yet. Ask about this sentence.",
        comments: "No comments yet. Be the first to comment.",
        translations: "No translation suggestions yet. Help improve the translation.",
      };
      empty.textContent = emptyMessages[currentTab];
      listEl.appendChild(empty);
      return;
    }
    entries.forEach((entry) => {
      listEl.appendChild(renderEntry(entry));
    });
  }

  toggle.addEventListener("click", () => {
    panel.classList.add("open");
    renderList();
  });

  closeBtn.addEventListener("click", () => {
    panel.classList.remove("open");
  });

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      currentTab = tab.dataset.tab;
      renderList();
    });
  });

  sortOrder.addEventListener("change", renderList);

  submitBtn.addEventListener("click", () => {
    const author = authorName.value.trim();
    const body = entryBody.value.trim();
    if (!author || !body) {
      alert("Please enter your name and a message.");
      return;
    }
    const entry = CommunityService.addEntry({
      lessonId: currentLessonId || getLessonId(),
      type: getEntryType(),
      authorDisplayName: author,
      body: body,
    });
    entryBody.value = "";
    renderList();
  });

  CommunityService.subscribe(renderList);
})();
