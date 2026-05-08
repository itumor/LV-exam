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

const aiService = new window.AIExplanationService();
let currentExplanationSentence = null;

const aiPanel = document.querySelector("#aiPanel");
const aiPanelContent = document.querySelector("#aiPanelContent");
const aiLoading = document.querySelector("#aiLoading");
const aiError = document.querySelector("#aiError");
const aiOverlay = document.querySelector("#aiOverlay");
const closeAIPanelBtn = document.querySelector("#closeAIPanel");
const aiModeToggle = document.querySelector("#aiModeToggle");
const retryBtn = document.querySelector("#retryBtn");

function openAIPanel() {
  aiPanel.classList.add("open");
  aiPanel.setAttribute("aria-hidden", "false");
  aiOverlay.hidden = false;
}

function closeAIPanel() {
  aiPanel.classList.remove("open");
  aiPanel.setAttribute("aria-hidden", "true");
  aiOverlay.hidden = true;
}

closeAIPanelBtn.addEventListener("click", closeAIPanel);
aiOverlay.addEventListener("click", closeAIPanel);

aiModeToggle.addEventListener("change", (e) => {
  aiService.setExplanationMode(e.target.checked ? "detailed" : "simple");
  if (currentExplanationSentence) {
    fetchExplanation(currentExplanationSentence);
  }
});

retryBtn.addEventListener("click", () => {
  if (currentExplanationSentence) {
    fetchExplanation(currentExplanationSentence);
  }
});

function parseTranscriptToSentences(text) {
  if (!text) return [];
  const sentences = text
    .split(/(?<=[.!?])\s+/)
    .map(s => s.trim())
    .filter(s => s.length > 0);
  return sentences;
}

function renderTranscriptWithClickableSentences(text) {
  const sentences = parseTranscriptToSentences(text);
  if (sentences.length === 0) {
    return text;
  }

  return sentences
    .map(
      (sentence, idx) =>
        `<span class="sentence-block" data-sentence="${idx}" title="Click for AI explanation">${escapeHtml(sentence)}</span>`
    )
    .join(" ");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function fetchExplanation(sentence) {
  aiLoading.hidden = false;
  aiError.hidden = true;
  aiPanelContent.innerHTML = "";

  const item = filtered[selectedIndex];
  const lessonId = item ? item.id : "default";
  aiService.setLessonId(lessonId);

  try {
    const explanation = await aiService.explainSentence(sentence, { lessonId });
    displayExplanation(explanation, sentence);
  } catch (err) {
    console.error("AI explanation error:", err);
    aiLoading.hidden = true;
    aiError.hidden = false;
  }
}

function displayExplanation(explanation, sentence) {
  aiLoading.hidden = true;

  let html = `
    <div class="explanation-section">
      <h4>Natural Translation</h4>
      <p>${escapeHtml(explanation.naturalTranslation)}</p>
    </div>
  `;

  if (explanation.literalTranslation && explanation.literalTranslation !== explanation.naturalTranslation) {
    html += `
      <div class="explanation-section">
        <h4>Word-by-Word</h4>
        <p>${escapeHtml(explanation.literalTranslation)}</p>
      </div>
    `;
  }

  if (explanation.vocabulary && explanation.vocabulary.length > 0) {
    html += `<div class="explanation-section"><h4>Key Vocabulary</h4>`;
    explanation.vocabulary.forEach(v => {
      html += `
        <div class="vocab-item">
          <span class="vocab-word">${escapeHtml(v.word)}</span>
          <span class="vocab-pos">${escapeHtml(v.pos || "")}</span>
          <div class="vocab-meaning">${escapeHtml(v.meaning || "")}</div>
          ${v.example ? `<div class="vocab-example">${escapeHtml(v.example)}</div>` : ""}
        </div>
      `;
    });
    html += `</div>`;
  }

  if (explanation.grammarNotes && explanation.grammarNotes.length > 0) {
    html += `<div class="explanation-section"><h4>Grammar Notes</h4>`;
    explanation.grammarNotes.forEach(g => {
      html += `<div class="grammar-note"><p>${escapeHtml(g)}</p></div>`;
    });
    html += `</div>`;
  }

  if (explanation.verbForms && explanation.verbForms.length > 0) {
    html += `<div class="explanation-section"><h4>Verb Forms</h4>`;
    explanation.verbForms.forEach(v => {
      html += `
        <span class="verb-form" title="${escapeHtml(v.meaning || "")}">
          ${escapeHtml(v.form || v.verb)}
        </span>
      `;
    });
    html += `</div>`;
  }

  if (explanation.caseNotes && explanation.caseNotes.length > 0) {
    html += `<div class="explanation-section"><h4>Case Notes</h4>`;
    explanation.caseNotes.forEach(c => {
      html += `
        <div class="grammar-note">
          <div class="grammar-note-title">${escapeHtml(c.case)}</div>
          <p>${escapeHtml(c.explanation)}</p>
        </div>
      `;
    });
    html += `</div>`;
  }

  if (explanation.whyThisForm && explanation.whyThisForm.length > 0) {
    html += `<div class="explanation-section"><h4>Why This Form?</h4>`;
    explanation.whyThisForm.forEach(w => {
      html += `
        <div class="grammar-note">
          <p><strong>${escapeHtml(w.phrase || "Explanation")}:</strong> ${escapeHtml(w.explanation || w.pattern || "")}</p>
        </div>
      `;
    });
    html += `</div>`;
  }

  aiPanelContent.innerHTML = html;
}

lvText.addEventListener("click", (e) => {
  const target = e.target;
  
  if (target.classList.contains("word-highlight")) {
    const word = target.dataset.word;
    const sentence = target.closest(".sentence-block")?.textContent || "";
    fetchWordExplanation(word, sentence);
    return;
  }

  const sentenceBlock = target.closest(".sentence-block");
  if (sentenceBlock) {
    const sentences = parseTranscriptToSentences(lvText.textContent);
    const idx = parseInt(sentenceBlock.dataset.sentence, 10);
    if (!isNaN(idx) && sentences[idx]) {
      currentExplanationSentence = sentences[idx];
      openAIPanel();
      fetchExplanation(currentExplanationSentence);
    }
  }
});

async function fetchWordExplanation(word, sentence) {
  aiLoading.hidden = false;
  aiError.hidden = true;
  aiPanelContent.innerHTML = "";

  try {
    const explanation = await aiService.explainWord(word, sentence);
    displayWordExplanation(explanation);
  } catch (err) {
    console.error("AI word explanation error:", err);
    aiLoading.hidden = true;
    aiError.hidden = false;
  }
}

function displayWordExplanation(explanation) {
  aiLoading.hidden = true;

  const html = `
    <div class="word-explanation">
      <span class="word">${escapeHtml(explanation.word)}</span>
      ${explanation.lemma ? `<span class="lemma">(${escapeHtml(explanation.lemma)})</span>` : ""}
      ${explanation.partOfSpeech ? `<span class="pos">${escapeHtml(explanation.partOfSpeech)}</span>` : ""}
      <div class="meaning">${escapeHtml(explanation.meaning || "No explanation available")}</div>
      ${explanation.caseOrTense ? `<div><strong>Case/Tense:</strong> ${escapeHtml(explanation.caseOrTense)}</div>` : ""}
      ${explanation.simpleExample ? `<div class="example">Example: ${escapeHtml(explanation.simpleExample)}</div>` : ""}
      ${explanation.inContext ? `<div class="example"><em>In context: ${escapeHtml(explanation.inContext)}</em></div>` : ""}
    </div>
  `;

  aiPanelContent.innerHTML = html;
}

const originalSelectItem = selectItem;
selectItem = function (index) {
  originalSelectItem(index);
  if (index >= 0 && index < filtered.length) {
    const item = filtered[index];
    const transcript = lvText.textContent;
    if (transcript && transcript !== "Latvian transcript is not available yet." && transcript !== "No transcript selected.") {
      lvText.innerHTML = renderTranscriptWithClickableSentences(transcript);
    }
  }
};

const originalApplyFilter = applyFilter;
applyFilter = function () {
  originalApplyFilter();
  const transcript = lvText.textContent;
  if (transcript && transcript !== "Latvian transcript is not available yet." && transcript !== "No transcript selected.") {
    lvText.innerHTML = renderTranscriptWithClickableSentences(transcript);
  }
};

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
