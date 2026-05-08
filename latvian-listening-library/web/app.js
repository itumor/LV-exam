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
const culturalSection = document.querySelector("#culturalSection");
const culturalContainer = document.querySelector("#culturalContainer");

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
let culturalContexts = [];

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
  renderCulturalContexts(item.id);
}

function renderCulturalContexts(lessonId) {
  culturalContainer.innerHTML = "";
  const contexts = culturalContexts.filter(c => c.lesson_ids && c.lesson_ids.includes(lessonId));
  
  if (contexts.length === 0) {
    culturalSection.hidden = true;
    return;
  }
  
  culturalSection.hidden = false;
  
  for (const context of contexts) {
    const card = document.createElement("article");
    card.className = "cultural-card";
    
    const header = document.createElement("div");
    header.className = "cultural-header";
    
    const headerTitle = document.createElement("h3");
    headerTitle.className = "cultural-title";
    headerTitle.textContent = `${context.title} (${context.title_en})`;
    
    const expandBtn = document.createElement("button");
    expandBtn.type = "button";
    expandBtn.className = "cultural-expand";
    expandBtn.textContent = "Learn more";
    expandBtn.setAttribute("aria-expanded", "false");
    
    header.appendChild(headerTitle);
    header.appendChild(expandBtn);
    
    const content = document.createElement("div");
    content.className = "cultural-content";
    content.hidden = true;
    
    const explanation = document.createElement("p");
    explanation.className = "cultural-explanation";
    explanation.textContent = context.explanation;
    
    const practicalNote = document.createElement("div");
    practicalNote.className = "cultural-note";
    const noteTitle = document.createElement("strong");
    noteTitle.textContent = "💡 For Expats: ";
    practicalNote.appendChild(noteTitle);
    practicalNote.appendChild(document.createTextNode(context.practical_note));
    
    content.appendChild(explanation);
    content.appendChild(practicalNote);
    
    if (context.phrases && context.phrases.length > 0) {
      const phrasesSection = document.createElement("div");
      phrasesSection.className = "cultural-phrases";
      const phrasesTitle = document.createElement("h4");
      phrasesTitle.textContent = "Useful Phrases";
      phrasesSection.appendChild(phrasesTitle);
      
      for (const phrase of context.phrases) {
        const phraseItem = document.createElement("div");
        phraseItem.className = "phrase-item";
        
        const phraseText = document.createElement("div");
        phraseText.className = "phrase-text";
        
        const lvPhrase = document.createElement("span");
        lvPhrase.className = "phrase-lv";
        lvPhrase.textContent = phrase.lv;
        
        const enPhrase = document.createElement("span");
        enPhrase.className = "phrase-en";
        enPhrase.textContent = phrase.en;
        
        phraseText.appendChild(lvPhrase);
        phraseText.appendChild(document.createTextNode(" — "));
        phraseText.appendChild(enPhrase);
        
        const phraseUsage = document.createElement("small");
        phraseUsage.className = "phrase-usage";
        phraseUsage.textContent = phrase.usage;
        
        phraseItem.appendChild(phraseText);
        phraseItem.appendChild(phraseUsage);
        phrasesSection.appendChild(phraseItem);
      }
      content.appendChild(phrasesSection);
    }
    
    if (context.related_vocabulary && context.related_vocabulary.length > 0) {
      const vocabSection = document.createElement("div");
      vocabSection.className = "cultural-vocab";
      const vocabTitle = document.createElement("h4");
      vocabTitle.textContent = "Related Vocabulary";
      vocabSection.appendChild(vocabTitle);
      
      const vocabList = document.createElement("div");
      vocabList.className = "vocab-list";
      for (const word of context.related_vocabulary) {
        const vocabWord = document.createElement("span");
        vocabWord.className = "vocab-word";
        vocabWord.textContent = word;
        vocabList.appendChild(vocabWord);
      }
      vocabSection.appendChild(vocabList);
      content.appendChild(vocabSection);
    }
    
    expandBtn.addEventListener("click", () => {
      const expanded = expandBtn.getAttribute("aria-expanded") === "true";
      expandBtn.setAttribute("aria-expanded", String(!expanded));
      expandBtn.textContent = expanded ? "Learn more" : "Show less";
      content.hidden = expanded;
    });
    
    card.appendChild(header);
    card.appendChild(content);
    culturalContainer.appendChild(card);
  }
}

function applyFilter() {
  const query = search.value.trim().toLowerCase();
  
  if (query && culturalContexts.length > 0) {
    const matchingContextIds = culturalContexts
      .filter(c => {
        const haystack = [c.title, c.title_en, c.explanation, ...(c.related_vocabulary || [])].join(" ").toLowerCase();
        return haystack.includes(query);
      })
      .flatMap(c => c.lesson_ids || []);
    
    const textMatches = catalog.filter((item) => {
      const haystack = [item.title, item.original_filename, item.level, item.status, item.lv_text, item.en_text]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
    
    const contextMatches = catalog.filter(item => matchingContextIds.includes(item.id));
    const combinedIds = [...new Set([...textMatches.map(i => i.id), ...contextMatches.map(i => i.id)])];
    filtered = catalog.filter(item => combinedIds.includes(item.id));
  } else {
    filtered = catalog.filter((item) => {
      const haystack = [item.title, item.original_filename, item.level, item.status, item.lv_text, item.en_text]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }
  
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
    culturalSection.hidden = true;
  }
}

previousButton.addEventListener("click", () => selectItem(selectedIndex - 1));
nextButton.addEventListener("click", () => selectItem(selectedIndex + 1));
search.addEventListener("input", applyFilter);

Promise.all([
  fetch("catalog.json", { cache: "no-store" }).then(r => r.json()),
  fetch("contexts.json", { cache: "no-store" }).then(r => r.json()).catch(() => [])
])
  .then(([items, contexts]) => {
    catalog = Array.isArray(items) ? items : [];
    culturalContexts = Array.isArray(contexts) ? contexts : [];
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
    setText(subtitle, "Run scripts/build_catalog.py after processing files.", "");
  });
