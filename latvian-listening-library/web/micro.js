const deck = document.querySelector("#feedDeck");
const levelFilter = document.querySelector("#levelFilter");
const feedLoading = document.querySelector("#feedLoading");
const feedEmpty = document.querySelector("#feedEmpty");
const feedCount = document.querySelector("#feedCount");
const feedProgress = document.querySelector("#feedProgress");
const toast = document.querySelector("#toast");

const CLIP_MIN_SECONDS = 15;
const CLIP_MAX_SECONDS = 45;
const FEED_PROGRESS_KEY = "latvian_listening_feed_progress";
const FALLBACK_OPTIONS = [
  "Labdien!",
  "Paldies!",
  "Lūdzu!",
  "Uz redzesanos!",
  "Es nesaprotu.",
  "Kur ir pietura?",
  "Cik tas maksā?",
  "Mani sauc Jānis."
];
const QUIZ_LEVELS = [
  { key: "easy", label: "Easy" },
  { key: "intermediate", label: "Intermediate" },
  { key: "hard", label: "Hard" },
  { key: "super", label: "Super" }
];

let allClips = [];
let filteredClips = [];
let activeIndex = 0;
let activeAudio = null;
let observer = null;
let currentRecorder = null;
let currentStream = null;
let currentRecognition = null;
let currentRecognitionText = "";
let currentRecordingCard = null;
const recordingUrls = {};

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function formatTime(seconds) {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  const total = Math.floor(safe);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
}

function hashString(value) {
  let hash = 0;
  const text = String(value || "");
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0;
  }
  return Math.abs(hash);
}

function rgbForClip(clip) {
  const palettes = [
    "18, 95, 74",
    "126, 45, 83",
    "125, 72, 34",
    "79, 76, 132",
    "89, 95, 39",
    "132, 55, 42",
    "52, 103, 91",
    "114, 58, 104"
  ];
  return palettes[hashString(clip.id || clip.title) % palettes.length];
}

function getFirstSentence(text) {
  const clean = String(text || "")
    .replace(/\s+/g, " ")
    .trim();
  if (!clean) return "";
  const sentenceMatch = clean.match(/^.{18,180}?[.!?](?:\s|$)/);
  const sentence = sentenceMatch ? sentenceMatch[0] : clean.slice(0, 160);
  return sentence.replace(/\s+/g, " ").trim();
}

function stripLessonMarker(text) {
  return String(text || "")
    .replace(/^\s*(?:\d+(?:[.,_]\d+)*\s*[.,]?\s*)+/u, "")
    .replace(/^(klausies|lasi|klausies\s+lasi|klausies\s+un\s+lasi)[.!:,\s-]*/iu, "")
    .replace(/\s+/g, " ")
    .trim();
}

function splitSentences(text) {
  const matches = String(text || "")
    .replace(/\s+/g, " ")
    .trim()
    .match(/[^.!?]+[.!?]?/g);
  return (matches || [])
    .map((sentence) => stripLessonMarker(sentence))
    .filter((sentence) => sentence.length >= 8);
}

function getClipSentences(text) {
  const sentences = splitSentences(text);
  return sentences.length ? sentences.slice(0, 6) : [stripLessonMarker(getFirstSentence(text))].filter(Boolean);
}

function isInstructionSentence(sentence) {
  const comparable = normalizeComparable(sentence);
  return /^(klausies|lasi|raksti|atzime|atzimet|nosauc|papildini|izpeti|labo|sakarto|pasvitro)\b/u.test(comparable)
    && comparable.length < 90;
}

function getFullTranscriptSentences(text) {
  const sentences = splitSentences(text);
  const contentSentences = sentences.filter((sentence) => !isInstructionSentence(sentence));
  const usableSentences = contentSentences.length ? contentSentences : sentences;
  return usableSentences.length ? usableSentences : [stripLessonMarker(getFirstSentence(text))].filter(Boolean);
}

function pickTranscriptSentence(sentences, ratio) {
  if (!sentences.length) return "";
  const index = clamp(Math.round((sentences.length - 1) * ratio), 0, sentences.length - 1);
  return sentences[index];
}

function normalizeComparable(text) {
  return String(text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^\p{L}\p{M}\p{N}\s-]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function uniqueTexts(values) {
  const seen = new Set();
  const result = [];
  values.forEach((value) => {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    const key = normalizeComparable(text);
    if (text && key && !seen.has(key)) {
      seen.add(key);
      result.push(text);
    }
  });
  return result;
}

function seededShuffle(values, seedText) {
  const result = values.slice();
  let seed = hashString(seedText) || 1;
  for (let index = result.length - 1; index > 0; index -= 1) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const swapIndex = seed % (index + 1);
    const tmp = result[index];
    result[index] = result[swapIndex];
    result[swapIndex] = tmp;
  }
  return result;
}

function summarizeText(text, maxLength) {
  const clean = String(text || "")
    .replace(/\s+/g, " ")
    .trim();
  if (clean.length <= maxLength) return clean;
  return `${clean.slice(0, maxLength - 1).trim()}…`;
}

function normalizeClipWindow(clip) {
  const start = Math.max(0, Number(clip.start) || 0);
  const requestedEnd = Number(clip.end);
  const rawEnd = Number.isFinite(requestedEnd) && requestedEnd > start ? requestedEnd : start + CLIP_MAX_SECONDS;
  const normalizedDuration = clamp(rawEnd - start, CLIP_MIN_SECONDS, CLIP_MAX_SECONDS);
  return {
    start,
    end: start + normalizedDuration,
    duration: normalizedDuration
  };
}

function normalizeCategory(value) {
  return String(value || "listening")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function inferCategory(lesson) {
  const haystack = [
    lesson.category,
    lesson.lesson_group,
    lesson.title,
    lesson.lv_text,
    lesson.en_text
  ].join(" ").toLowerCase();

  if (/autobus|tramvaj|vilcien|stacij|transport|brauc/.test(haystack)) return "transport";
  if (/veikal|pirkt|cena|eiro|nauda|maksa/.test(haystack)) return "shopping";
  if (/darbs|strada|profes|kol[eē]g/.test(haystack)) return "work";
  if (/gimene|mamma|t[eē]vs|bralis|masa|b[eē]rn/.test(haystack)) return "family";
  if (/arst|slimn|vesel|z[aā]l/.test(haystack)) return "health";
  if (/kafej|ed|dzert|maiz|kuka/.test(haystack)) return "food";
  if (/laiks|pulksten|diena|rit|vakar/.test(haystack)) return "time";
  if (/viesnic|lidost|ce[ļl]oj|j[uū]rmal/.test(haystack)) return "travel";
  return normalizeCategory(lesson.lesson_group || lesson.category || "daily life");
}

function pickPhrase(text, fallback) {
  const sentence = getClipSentences(text)[0] || getFirstSentence(text);
  if (sentence) {
    return summarizeText(sentence, 86);
  }
  return fallback || "Labdien!";
}

function getPoolPhrases(pool, index, field, fallbackField) {
  const phrases = [];
  for (let offset = 1; phrases.length < 8 && offset < pool.length; offset += 1) {
    const other = pool[(index + offset * 7) % pool.length];
    if (other && other[field]) {
      phrases.push(pickPhrase(other[field], other[fallbackField] || other.title));
    }
  }
  return uniqueTexts(phrases);
}

function getWords(text) {
  return String(text || "")
    .toLowerCase()
    .match(/[\p{L}\p{M}]{4,}/gu) || [];
}

function pickClozeWord(sentence, seedText) {
  const words = uniqueTexts(getWords(sentence));
  if (!words.length) return "";
  return words[hashString(seedText) % words.length];
}

function makeClozeSentence(sentence, word) {
  if (!word) return sentence;
  const escapedWord = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return sentence.replace(new RegExp(escapedWord, "iu"), "_____");
}

function buildDetailStatement(sentence) {
  const clean = stripLessonMarker(sentence);
  return summarizeText(clean, 110);
}

function makeQuestion(level, prompt, promptLv, correct, distractors, seedText, explanation) {
  const safeCorrect = summarizeText(correct, 116);
  const options = uniqueTexts([safeCorrect].concat(distractors.map((value) => summarizeText(value, 116))));

  for (let index = 0; options.length < 3 && index < FALLBACK_OPTIONS.length; index += 1) {
    options.push(FALLBACK_OPTIONS[index]);
  }

  const finalOptions = seededShuffle(options.slice(0, 3), `${seedText}-${level}`);
  const answer = finalOptions.findIndex((option) => normalizeComparable(option) === normalizeComparable(safeCorrect));

  return {
    level,
    prompt,
    prompt_lv: promptLv,
    options: finalOptions,
    answer: answer >= 0 ? answer : 0,
    answer_text: safeCorrect,
    explanation: explanation || ""
  };
}

function buildQuizLevels(source, pool, index) {
  const lvSentences = getFullTranscriptSentences(source.lv_text || source.transcript);
  const enSentences = getFullTranscriptSentences(source.en_text || source.translation);
  const primaryLv = pickTranscriptSentence(lvSentences, 0) || source.answer_text || source.title || "Labdien!";
  const primaryEn = pickTranscriptSentence(enSentences, 0.35) || source.translation || "Listen for the main meaning.";
  const detailSentence = pickTranscriptSentence(lvSentences, 0.5) || primaryLv;
  const superSentence = pickTranscriptSentence(lvSentences, 0.82) || detailSentence;
  const clozeWord = pickClozeWord(detailSentence, `${source.id || source.title}-hard`);
  const clozeSentence = makeClozeSentence(detailSentence, clozeWord);
  const lvDistractors = getPoolPhrases(pool, index, "lv_text", "title");
  const enDistractors = getPoolPhrases(pool, index, "en_text", "title");
  const wordDistractors = uniqueTexts(lvDistractors.flatMap(getWords)).filter((word) => normalizeComparable(word) !== normalizeComparable(clozeWord));
  const detailDistractors = lvDistractors.map(buildDetailStatement);

  return {
    easy: makeQuestion(
      "easy",
      "Which Latvian line appears in the full audio?",
      "Kura latviešu frāze ir pilnajā audio?",
      primaryLv,
      lvDistractors,
      `${source.id || source.title}-easy`,
      "Focus on recognition: match the full audio to the exact Latvian line."
    ),
    intermediate: makeQuestion(
      "intermediate",
      "What is the best English meaning from the full audio?",
      "Kāda ir labākā nozīme pilnajā audio?",
      primaryEn,
      enDistractors,
      `${source.id || source.title}-intermediate`,
      "Focus on meaning across the full transcript, not only the first clip."
    ),
    hard: makeQuestion(
      "hard",
      `Which full-audio word completes: ${clozeSentence}`,
      `Kurš pilnā audio vārds der teikumā: ${clozeSentence}`,
      clozeWord || primaryLv,
      wordDistractors,
      `${source.id || source.title}-hard`,
      "Focus on detail: catch the missing word from the full audio."
    ),
    super: makeQuestion(
      "super",
      "Which detail is stated in the full audio?",
      "Kura detaļa ir dzirdama pilnajā audio?",
      buildDetailStatement(superSentence),
      detailDistractors,
      `${source.id || source.title}-super`,
      "Focus on comprehension: choose the supported detail from the full audio."
    )
  };
}

function clipFromLesson(lesson, pool, index) {
  const quizLevels = buildQuizLevels(lesson, pool, index);
  const quiz = quizLevels.easy;
  const clipWindow = normalizeClipWindow({ start: 0, end: CLIP_MAX_SECONDS });
  const title = lesson.title || lesson.original_filename || `Audio ${index + 1}`;
  const transcript = lesson.lv_text || "";
  const translation = lesson.en_text || "";
  const shadowPhrase = pickPhrase(transcript, quiz.answer_text);

  return {
    id: `feed-${lesson.id || index}`,
    sourceLessonId: lesson.id,
    audio_url: lesson.audio_url,
    title,
    prompt: quiz.prompt,
    prompt_lv: quiz.prompt_lv,
    options: quiz.options,
    answer: quiz.answer,
    answer_text: quiz.answer_text,
    quizLevels,
    transcript,
    translation,
    difficulty: lesson.level || "A1",
    category: inferCategory(lesson),
    description: lesson.lesson_group || lesson.original_filename || "Listening library",
    start: clipWindow.start,
    end: clipWindow.end,
    duration: clipWindow.duration,
    shadowPhrase,
    source: "catalog"
  };
}

function normalizeCuratedClip(clip, index, pool, catalogLesson) {
  const clipWindow = normalizeClipWindow(clip);
  const transcript = catalogLesson && catalogLesson.lv_text ? catalogLesson.lv_text : clip.transcript || "";
  const translation = catalogLesson && catalogLesson.en_text ? catalogLesson.en_text : clip.translation || "";
  const source = {
    id: clip.id || `micro-${index + 1}`,
    title: clip.title || `Clip ${index + 1}`,
    lv_text: transcript,
    en_text: translation,
    answer_text: clip.answer_text || ""
  };
  const quizPool = (Array.isArray(pool) ? pool : []).map((item) => ({
    id: item.id,
    title: item.title,
    lv_text: item.lv_text || item.transcript || "",
    en_text: item.en_text || item.translation || ""
  }));
  const quizLevels = buildQuizLevels(source, quizPool, index);
  if (!catalogLesson) {
    const easyOptions = Array.isArray(clip.options) && clip.options.length ? clip.options.slice(0, 3) : quizLevels.easy.options;
    const easyAnswer = Number.isInteger(clip.answer) ? clamp(clip.answer, 0, easyOptions.length - 1) : quizLevels.easy.answer;
    quizLevels.easy = {
      level: "easy",
      prompt: clip.prompt || quizLevels.easy.prompt,
      prompt_lv: clip.prompt_lv || quizLevels.easy.prompt_lv,
      options: easyOptions,
      answer: easyAnswer,
      answer_text: clip.answer_text || easyOptions[easyAnswer] || quizLevels.easy.answer_text,
      explanation: "Focus on recognition: match the full audio to the exact Latvian line."
    };
  }

  return {
    id: source.id,
    sourceLessonId: catalogLesson && catalogLesson.id ? catalogLesson.id : clip.sourceLessonId || clip.id,
    audio_url: catalogLesson && catalogLesson.audio_url ? catalogLesson.audio_url : clip.audio_url,
    title: source.title,
    prompt: quizLevels.easy.prompt,
    prompt_lv: quizLevels.easy.prompt_lv,
    options: quizLevels.easy.options,
    answer: quizLevels.easy.answer,
    answer_text: quizLevels.easy.answer_text,
    quizLevels,
    transcript,
    translation,
    difficulty: catalogLesson && catalogLesson.level ? catalogLesson.level : clip.difficulty || "A1",
    category: normalizeCategory(clip.category || (catalogLesson && catalogLesson.lesson_group) || "daily life"),
    description: clip.description || (catalogLesson && (catalogLesson.lesson_group || catalogLesson.original_filename)) || "Curated micro clip",
    start: clipWindow.start,
    end: clipWindow.end,
    duration: clipWindow.duration,
    shadowPhrase: pickPhrase(transcript, quizLevels.easy.answer_text),
    source: "curated"
  };
}

function mergeClips(curated, catalog) {
  const usableCatalog = (Array.isArray(catalog) ? catalog : []).filter((lesson) => {
    return lesson && lesson.audio_url && lesson.status === "completed";
  });
  const catalogByAudioUrl = new Map(usableCatalog.map((lesson) => [lesson.audio_url, lesson]));
  const normalizedCurated = (Array.isArray(curated) ? curated : [])
    .filter((clip) => clip && clip.audio_url)
    .map((clip, index) => normalizeCuratedClip(clip, index, usableCatalog, catalogByAudioUrl.get(clip.audio_url)));
  const audioUrls = new Set(normalizedCurated.map((clip) => clip.audio_url));
  const generated = usableCatalog
    .filter((lesson) => !audioUrls.has(lesson.audio_url))
    .map((lesson, index) => clipFromLesson(lesson, usableCatalog, index));

  return normalizedCurated.concat(generated);
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) {
    throw new Error(`Unable to load ${path}`);
  }
  return response.json();
}

function getDefaultMicroClips() {
  return [
    {
      id: "micro-001",
      audio_url: "data/A1_klausisanas/audio/1_2.mp3",
      title: "Iepazīšanās",
      prompt: "Which Latvian line is in the full audio?",
      prompt_lv: "Kura latviešu frāze ir pilnajā audio?",
      options: ["Mani sauc Natālija.", "Mani sauc Sāra.", "Es dzīvoju Rīgā."],
      answer: 0,
      answer_text: "Mani sauc Natālija.",
      transcript: "1. 2. Klausies un atkārto. Labrīt! Mani sauc Jānis Vaivats. Es esmu pasniedzējis. Labdien! Kā jūs sauc? Mani sauc Natālija. Esmu studente. Labvakar! Vai tu esi Gunta? Jā. Un tu esi Aigars? Tu esi Andris? Nē, es neesmu Andris, es esmu Edgars.",
      translation: "2. Listen and repeat. Good morning! My name is John Wyvat. I'm a teacher. Hello! What's your name? I'm Natalie. I'm a student. Good evening! Are you Gunta? Yeah. And you're Aigars? Are you Andris? No, I'm not Andris, I'm Edgars.",
      difficulty: "A1",
      category: "greetings",
      start: 0,
      end: 15
    },
    {
      id: "micro-002",
      audio_url: "data/A1_klausisanas/audio/1_3.mp3",
      title: "Vārds",
      prompt: "Which name appears in the full audio?",
      prompt_lv: "Kurš vārds ir pilnajā audio?",
      options: ["Kaspars", "Juris", "Ilze"],
      answer: 0,
      answer_text: "Kaspars",
      transcript: "1. 3. Klausies un raksti. Labvakar, es esmu Maija. Labvakar, bet es esmu Kaspars. Labvakar, vai tu esi Aina? Nē, es neesmu Aina, es esmu Maija. Labrīt, mani sauc Deivits, kā tevi sauc? Mani sauc Sāra.",
      translation: "3: Listen and write. Good evening, I'm Maya. Good evening, but I'm Cameron. Good evening, are you Aina? No, I'm not Aina, I'm Maija. Good morning, my name's Davit, what's your name? My name is Sarah.",
      difficulty: "A1",
      category: "people",
      start: 0,
      end: 15
    }
  ];
}

async function loadFeedData() {
  const [clipResult, catalogResult] = await Promise.allSettled([
    fetchJson("microClips.json"),
    fetchJson("catalog.json")
  ]);

  const curated = clipResult.status === "fulfilled" ? clipResult.value : getDefaultMicroClips();
  const catalog = catalogResult.status === "fulfilled" ? catalogResult.value : [];
  return mergeClips(curated, catalog);
}

function getSavedProgress() {
  try {
    return JSON.parse(localStorage.getItem(FEED_PROGRESS_KEY)) || {};
  } catch (error) {
    return {};
  }
}

function saveProgress(clip, action) {
  const progress = getSavedProgress();
  progress[clip.id] = {
    id: clip.id,
    title: clip.title,
    action,
    updatedAt: new Date().toISOString()
  };
  localStorage.setItem(FEED_PROGRESS_KEY, JSON.stringify(progress));
}

function getQuiz(clip, level) {
  if (clip.quizLevels && clip.quizLevels[level]) return clip.quizLevels[level];
  return {
    level: "easy",
    prompt: clip.prompt,
    prompt_lv: clip.prompt_lv,
    options: clip.options,
    answer: clip.answer,
    answer_text: clip.answer_text,
    explanation: ""
  };
}

function renderOptions(question) {
  return question.options.map((option, index) => {
    return `<button class="feed-option" type="button" data-answer-index="${index}">${escapeHtml(option)}</button>`;
  }).join("");
}

function renderQuizLevelButtons() {
  return QUIZ_LEVELS.map((level, index) => {
    return `<button class="quiz-level-btn ${index === 0 ? "active" : ""}" type="button" data-quiz-level="${level.key}" aria-pressed="${index === 0 ? "true" : "false"}">${escapeHtml(level.label)}</button>`;
  }).join("");
}

function renderClip(clip, index) {
  const question = getQuiz(clip, "easy");
  const transcript = clip.transcript || "Transcript unavailable.";
  const translation = clip.translation || "Translation unavailable.";
  const sourceLabel = clip.source === "curated" ? "Curated" : "Library";
  const rangeLabel = `${formatTime(clip.start)}-${formatTime(clip.end)}`;

  return `
    <section class="feed-card" data-index="${index}" data-clip-id="${escapeHtml(clip.id)}" data-active-quiz-level="easy" data-playback-mode="clip" style="--card-rgb: ${rgbForClip(clip)}">
      <div class="feed-main">
        <div class="feed-meta">
          <span class="feed-pill">${escapeHtml(sourceLabel)}</span>
          <span class="feed-pill">${escapeHtml(clip.difficulty)}</span>
          <span class="feed-pill">${escapeHtml(clip.category)}</span>
          <span class="feed-pill">${escapeHtml(rangeLabel)}</span>
        </div>

        <h1 class="feed-title">${escapeHtml(clip.title)}</h1>
        <p class="feed-copy">${escapeHtml(clip.description || "Swipe through short Latvian listening reps.")}</p>

        <div class="feed-player" aria-label="Listening audio player">
          <audio preload="none" data-src="${escapeHtml(clip.audio_url)}"></audio>
          <div class="feed-player-top">
            <button class="feed-play" type="button" data-action="play" aria-label="Play clip">
              <span aria-hidden="true">▶</span>
            </button>
            <div class="feed-timebox">
              <div class="feed-time-row">
                <span data-role="elapsed">${formatTime(0)}</span>
                <span data-role="duration-label">Clip ${escapeHtml(rangeLabel)}</span>
              </div>
              <input class="feed-range" type="range" min="0" max="${clip.duration}" value="0" step="0.1" data-action="seek" aria-label="Seek within selected audio mode" />
              <div class="playback-mode" role="group" aria-label="Audio playback length">
                <button class="playback-mode-btn active" type="button" data-playback-mode="clip" aria-pressed="true">Clip</button>
                <button class="playback-mode-btn" type="button" data-playback-mode="full" aria-pressed="false">Full</button>
              </div>
            </div>
          </div>
        </div>

        <section class="feed-quiz" aria-label="Instant quiz from full audio">
          <span class="feed-panel-label">Instant quiz</span>
          <div class="quiz-levels" role="group" aria-label="Quiz difficulty">
            ${renderQuizLevelButtons()}
          </div>
          <h2 data-role="quiz-prompt">${escapeHtml(question.prompt_lv || question.prompt)}</h2>
          <div class="feed-options" data-role="quiz-options">${renderOptions(question)}</div>
          <p class="feed-feedback" data-role="feedback"></p>
        </section>

        <section class="feed-shadow" aria-label="Shadow speaking">
          <span class="feed-panel-label">Shadow speaking</span>
          <h2>Repeat this line after the speaker.</h2>
          <p class="feed-shadow-text">${escapeHtml(clip.shadowPhrase || clip.answer_text)}</p>
          <div class="shadow-actions">
            <button class="shadow-btn" type="button" data-action="shadow-start">Record</button>
            <button class="shadow-btn secondary" type="button" data-action="shadow-stop" disabled>Stop</button>
            <button class="shadow-btn secondary" type="button" data-action="shadow-play" disabled>Play mine</button>
          </div>
          <p class="shadow-status" data-role="shadow-status"></p>
        </section>

        <section class="feed-transcript" data-role="transcript">
          <div class="transcript-heading">
            <span class="feed-panel-label">Full transcript</span>
            <button class="transcript-close" type="button" data-action="transcript" aria-label="Close transcript">×</button>
          </div>
          <div class="feed-transcript-body">
            <p><strong>LV:</strong> ${escapeHtml(transcript)}</p>
            <p><strong>EN:</strong> ${escapeHtml(translation)}</p>
          </div>
        </section>
      </div>

      <aside class="feed-rail" aria-label="Feed actions">
        <button class="rail-btn" type="button" title="Previous clip" aria-label="Previous clip" data-action="previous">↑</button>
        <button class="rail-btn" type="button" title="Show transcript" aria-label="Show transcript" data-action="transcript">T</button>
        <button class="rail-btn" type="button" title="Save clip" aria-label="Save clip" data-action="save">★</button>
        <button class="rail-btn" type="button" title="Copy link" aria-label="Copy link" data-action="share">↗</button>
        <button class="rail-btn" type="button" title="Next clip" aria-label="Next clip" data-action="next">↓</button>
        <div class="rail-stat">${index + 1}<br/>${filteredClips.length}</div>
      </aside>
    </section>
  `;
}

function setActiveIndex(index, updateUrl) {
  activeIndex = clamp(index, 0, Math.max(filteredClips.length - 1, 0));
  if (feedCount) {
    feedCount.textContent = `${filteredClips.length ? activeIndex + 1 : 0} / ${filteredClips.length}`;
  }
  if (feedProgress) {
    const pct = filteredClips.length ? ((activeIndex + 1) / filteredClips.length) * 100 : 0;
    feedProgress.style.width = `${pct}%`;
  }
  if (updateUrl && filteredClips[activeIndex]) {
    const params = new URLSearchParams(window.location.search);
    params.set("id", filteredClips[activeIndex].id);
    window.history.replaceState(null, "", `?${params.toString()}`);
  }
}

function pauseNonActiveAudio(activeCard) {
  deck.querySelectorAll("audio").forEach((audio) => {
    if (!activeCard || !activeCard.contains(audio)) {
      audio.pause();
      const card = audio.closest(".feed-card");
      setPlayButtonState(card, false);
    }
  });
}

function getAudioDuration(audio) {
  return audio && Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : null;
}

function getPlaybackMode(card) {
  return card && card.dataset.playbackMode === "full" ? "full" : "clip";
}

function getPlaybackBounds(card, clip, audio) {
  const mode = getPlaybackMode(card);
  const audioDuration = getAudioDuration(audio);

  if (mode === "full") {
    return {
      mode,
      start: 0,
      end: audioDuration || Number.POSITIVE_INFINITY,
      duration: audioDuration || clip.duration,
      hasKnownDuration: Boolean(audioDuration)
    };
  }

  const clipEnd = audioDuration ? Math.min(clip.end, audioDuration) : clip.end;
  return {
    mode,
    start: clip.start,
    end: clipEnd,
    duration: Math.max(1, clipEnd - clip.start),
    hasKnownDuration: true
  };
}

function updatePlaybackUi(card) {
  if (!card) return;
  const index = Number(card.dataset.index);
  const clip = filteredClips[index];
  const audio = card.querySelector("audio");
  const range = card.querySelector(".feed-range");
  const elapsed = card.querySelector('[data-role="elapsed"]');
  const durationLabel = card.querySelector('[data-role="duration-label"]');
  if (!clip || !audio || !range) return;

  const bounds = getPlaybackBounds(card, clip, audio);
  const progress = audio.getAttribute("src")
    ? clamp((audio.currentTime || bounds.start) - bounds.start, 0, bounds.duration)
    : 0;

  range.max = String(bounds.duration);
  range.value = String(progress);
  if (elapsed) elapsed.textContent = formatTime(progress);
  if (durationLabel) {
    durationLabel.textContent = bounds.mode === "full"
      ? `Full ${bounds.hasKnownDuration ? formatTime(bounds.duration) : "loading"}`
      : `Clip ${formatTime(bounds.start)}-${formatTime(bounds.end)}`;
  }

  card.querySelectorAll(".playback-mode-btn").forEach((button) => {
    const isActive = button.dataset.playbackMode === bounds.mode;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function setupObserver() {
  if (observer) observer.disconnect();
  observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting && entry.intersectionRatio >= 0.66) {
        const card = entry.target;
        const index = Number(card.dataset.index);
        setActiveIndex(index, true);
        pauseNonActiveAudio(card);
      }
    });
  }, {
    root: deck,
    threshold: [0.66]
  });

  deck.querySelectorAll(".feed-card").forEach((card) => observer.observe(card));
}

function wireAudioEvents() {
  deck.querySelectorAll(".feed-card").forEach((card) => {
    const index = Number(card.dataset.index);
    const clip = filteredClips[index];
    const audio = card.querySelector("audio");

    audio.addEventListener("loadedmetadata", () => {
      if (Number.isFinite(audio.duration) && audio.duration > 0 && audio.duration < clip.end) {
        clip.end = Math.max(clip.start, audio.duration);
        clip.duration = Math.max(1, clip.end - clip.start);
      }
      updatePlaybackUi(card);
    });

    audio.addEventListener("timeupdate", () => {
      const bounds = getPlaybackBounds(card, clip, audio);
      if (audio.currentTime < bounds.start) {
        audio.currentTime = bounds.start;
      }
      if (Number.isFinite(bounds.end) && audio.currentTime >= bounds.end) {
        audio.pause();
        audio.currentTime = bounds.start;
        setPlayButtonState(card, false);
        updatePlaybackUi(card);
        saveProgress(clip, bounds.mode === "full" ? "full-listened" : "listened");
        return;
      }
      updatePlaybackUi(card);
    });

    audio.addEventListener("play", () => {
      activeAudio = audio;
      setPlayButtonState(card, true);
      updatePlaybackUi(card);
    });

    audio.addEventListener("pause", () => {
      setPlayButtonState(card, false);
      updatePlaybackUi(card);
    });

    updatePlaybackUi(card);
  });
}

function setPlayButtonState(card, isPlaying) {
  if (!card) return;
  const button = card.querySelector('[data-action="play"] span');
  if (button) {
    button.textContent = isPlaying ? "Ⅱ" : "▶";
  }
}

function ensureAudioSource(audio) {
  if (!audio || audio.getAttribute("src")) return;
  const src = audio.dataset.src;
  if (src) {
    audio.setAttribute("src", src);
    audio.load();
  }
}

function setPlaybackMode(card, mode) {
  const index = Number(card.dataset.index);
  const clip = filteredClips[index];
  const audio = card.querySelector("audio");
  if (!clip || !audio) return;

  card.dataset.playbackMode = mode === "full" ? "full" : "clip";
  if (card.dataset.playbackMode === "full") {
    ensureAudioSource(audio);
  }

  const bounds = getPlaybackBounds(card, clip, audio);
  if (audio.getAttribute("src") && (audio.currentTime < bounds.start || (Number.isFinite(bounds.end) && audio.currentTime >= bounds.end))) {
    audio.currentTime = bounds.start;
  }
  updatePlaybackUi(card);
}

function scrollToClip(index) {
  const safeIndex = clamp(index, 0, Math.max(filteredClips.length - 1, 0));
  const target = deck.querySelector(`.feed-card[data-index="${safeIndex}"]`);
  if (target) {
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveIndex(safeIndex, true);
  }
}

function togglePlay(card) {
  const index = Number(card.dataset.index);
  const clip = filteredClips[index];
  const audio = card.querySelector("audio");
  if (!clip || !audio) return;

  if (activeAudio && activeAudio !== audio) {
    activeAudio.pause();
  }

  if (!audio.paused) {
    audio.pause();
    return;
  }

  ensureAudioSource(audio);
  const bounds = getPlaybackBounds(card, clip, audio);
  if (audio.currentTime < bounds.start || (Number.isFinite(bounds.end) && audio.currentTime >= bounds.end)) {
    audio.currentTime = bounds.start;
  }

  audio.play().catch(() => {
    showToast("Tap again to start audio.");
  });
}

function seekWithinClip(card, range) {
  const index = Number(card.dataset.index);
  const clip = filteredClips[index];
  const audio = card.querySelector("audio");
  if (!clip || !audio) return;
  ensureAudioSource(audio);
  const bounds = getPlaybackBounds(card, clip, audio);
  audio.currentTime = bounds.start + Number(range.value || 0);
  updatePlaybackUi(card);
}

function setQuizLevel(card, level) {
  const clip = filteredClips[Number(card.dataset.index)];
  const question = getQuiz(clip, level);
  setPlaybackMode(card, "full");
  card.dataset.activeQuizLevel = question.level || level;

  card.querySelectorAll(".quiz-level-btn").forEach((button) => {
    const isActive = button.dataset.quizLevel === card.dataset.activeQuizLevel;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
  });

  const prompt = card.querySelector('[data-role="quiz-prompt"]');
  const options = card.querySelector('[data-role="quiz-options"]');
  const feedback = card.querySelector('[data-role="feedback"]');
  if (prompt) prompt.textContent = question.prompt_lv || question.prompt;
  if (options) options.innerHTML = renderOptions(question);
  if (feedback) feedback.textContent = "";
}

function answerQuiz(button) {
  const card = button.closest(".feed-card");
  const index = Number(card.dataset.index);
  const clip = filteredClips[index];
  const level = card.dataset.activeQuizLevel || "easy";
  const question = getQuiz(clip, level);
  setPlaybackMode(card, "full");
  const selectedIndex = Number(button.dataset.answerIndex);
  const options = card.querySelectorAll(".feed-option");
  const feedback = card.querySelector('[data-role="feedback"]');
  const isCorrect = selectedIndex === question.answer;

  options.forEach((option) => {
    const optionIndex = Number(option.dataset.answerIndex);
    option.disabled = true;
    if (optionIndex === question.answer) option.classList.add("correct");
    if (optionIndex === selectedIndex && optionIndex !== question.answer) option.classList.add("incorrect");
  });

  feedback.textContent = isCorrect
    ? `Correct: ${question.answer_text}`
    : `Answer: ${question.answer_text}`;
  saveProgress(clip, isCorrect ? `quiz-${level}-correct` : `quiz-${level}-review`);
}

function toggleTranscript(card) {
  const transcript = card.querySelector('[data-role="transcript"]');
  if (transcript) {
    transcript.classList.toggle("open");
  }
}

function saveClip(card) {
  const clip = filteredClips[Number(card.dataset.index)];
  saveProgress(clip, "saved");
  showToast("Clip saved for review.");
}

async function shareClip(card) {
  const clip = filteredClips[Number(card.dataset.index)];
  const url = `${window.location.origin}${window.location.pathname}?id=${encodeURIComponent(clip.id)}`;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(url);
    showToast("Link copied.");
    return;
  }
  showToast(url);
}

function showToast(message) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.classList.remove("visible");
  }, 2400);
}

function normalizeSpeech(text) {
  return String(text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^\p{L}\p{M}\s-]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function tokenSimilarity(expected, actual) {
  const expectedTokens = new Set(normalizeSpeech(expected).split(" ").filter(Boolean));
  const actualTokens = new Set(normalizeSpeech(actual).split(" ").filter(Boolean));
  if (!expectedTokens.size || !actualTokens.size) return 0;
  let shared = 0;
  actualTokens.forEach((token) => {
    if (expectedTokens.has(token)) shared += 1;
  });
  return shared / expectedTokens.size;
}

function getSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return null;
  const recognition = new SpeechRecognition();
  recognition.lang = "lv-LV";
  recognition.continuous = false;
  recognition.interimResults = true;
  return recognition;
}

function setShadowButtons(card, state) {
  const start = card.querySelector('[data-action="shadow-start"]');
  const stop = card.querySelector('[data-action="shadow-stop"]');
  const play = card.querySelector('[data-action="shadow-play"]');
  if (start) start.disabled = state === "recording";
  if (stop) stop.disabled = state !== "recording";
  if (play) play.disabled = !recordingUrls[card.dataset.clipId] || state === "recording";
}

async function startShadow(card) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === "undefined") {
    setShadowStatus(card, "Recording is not available in this browser.");
    return;
  }

  stopShadow();
  const clip = filteredClips[Number(card.dataset.index)];
  const chunks = [];
  currentRecognitionText = "";
  currentRecordingCard = card;

  try {
    currentStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    currentRecorder = new MediaRecorder(currentStream);
  } catch (error) {
    currentRecordingCard = null;
    setShadowStatus(card, "Microphone permission is needed for shadow speaking.");
    return;
  }

  const recorder = currentRecorder;
  recorder.addEventListener("dataavailable", (event) => {
    if (event.data && event.data.size > 0) chunks.push(event.data);
  });

  recorder.addEventListener("stop", () => {
    const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
    if (recordingUrls[clip.id]) URL.revokeObjectURL(recordingUrls[clip.id]);
    recordingUrls[clip.id] = URL.createObjectURL(blob);
    setShadowButtons(card, "ready");
    currentRecordingCard = null;

    if (currentRecognitionText) {
      const match = Math.round(tokenSimilarity(clip.shadowPhrase, currentRecognitionText) * 100);
      setShadowStatus(card, `You said: "${currentRecognitionText}" · Match ${match}%`);
    } else {
      setShadowStatus(card, "Recording saved. Play it next to the original.");
    }
    saveProgress(clip, "shadow-recorded");
  });

  currentRecognition = getSpeechRecognition();
  if (currentRecognition) {
    currentRecognition.addEventListener("result", (event) => {
      let text = "";
      for (let index = 0; index < event.results.length; index += 1) {
        text += event.results[index][0].transcript;
      }
      currentRecognitionText = text.trim();
    });
    try {
      currentRecognition.start();
    } catch (error) {
      currentRecognition = null;
    }
  }

  recorder.start();
  setShadowButtons(card, "recording");
  setShadowStatus(card, "Recording... speak with the same rhythm.");
}

function stopShadow(card) {
  const targetCard = card || currentRecordingCard;
  if (currentRecognition) {
    try {
      currentRecognition.stop();
    } catch (error) {
      currentRecognition.abort();
    }
    currentRecognition = null;
  }

  if (currentRecorder && currentRecorder.state !== "inactive") {
    currentRecorder.stop();
  }

  if (currentStream) {
    currentStream.getTracks().forEach((track) => track.stop());
    currentStream = null;
  }

  currentRecorder = null;
  if (targetCard) setShadowButtons(targetCard, "ready");
}

function playShadowRecording(card) {
  const url = recordingUrls[card.dataset.clipId];
  if (!url) return;
  const playback = new Audio(url);
  playback.play().catch(() => showToast("Recording playback was blocked."));
}

function setShadowStatus(card, message) {
  if (!card) return;
  const status = card.querySelector('[data-role="shadow-status"]');
  if (status) status.textContent = message;
}

function renderFeed() {
  const level = levelFilter ? levelFilter.value : "all";
  filteredClips = allClips.filter((clip) => level === "all" || clip.difficulty === level);
  deck.innerHTML = "";

  if (feedLoading) feedLoading.classList.add("hidden");
  if (feedEmpty) feedEmpty.classList.toggle("hidden", filteredClips.length > 0);

  if (!filteredClips.length) {
    setActiveIndex(0, false);
    return;
  }

  deck.innerHTML = filteredClips.map(renderClip).join("");
  wireAudioEvents();
  setupObserver();

  const params = new URLSearchParams(window.location.search);
  const requestedId = params.get("id");
  const requestedIndex = filteredClips.findIndex((clip) => clip.id === requestedId);
  setActiveIndex(requestedIndex >= 0 ? requestedIndex : 0, false);
  window.requestAnimationFrame(() => scrollToClip(activeIndex));
}

deck.addEventListener("click", (event) => {
  const actionButton = event.target.closest("[data-action]");
  const answerButton = event.target.closest("[data-answer-index]");
  const quizLevelButton = event.target.closest(".quiz-level-btn[data-quiz-level]");
  const playbackModeButton = event.target.closest(".playback-mode-btn[data-playback-mode]");
  const card = event.target.closest(".feed-card");

  if (playbackModeButton && card) {
    setPlaybackMode(card, playbackModeButton.dataset.playbackMode);
    return;
  }

  if (quizLevelButton && card) {
    setQuizLevel(card, quizLevelButton.dataset.quizLevel);
    return;
  }

  if (answerButton && card) {
    answerQuiz(answerButton);
    return;
  }

  if (!actionButton || !card) return;

  const action = actionButton.dataset.action;
  if (action === "play") togglePlay(card);
  if (action === "previous") scrollToClip(Number(card.dataset.index) - 1);
  if (action === "next") scrollToClip(Number(card.dataset.index) + 1);
  if (action === "transcript") toggleTranscript(card);
  if (action === "save") saveClip(card);
  if (action === "share") shareClip(card).catch(() => showToast("Could not copy link."));
  if (action === "shadow-start") startShadow(card);
  if (action === "shadow-stop") stopShadow(card);
  if (action === "shadow-play") playShadowRecording(card);
});

deck.addEventListener("input", (event) => {
  const range = event.target.closest('[data-action="seek"]');
  const card = event.target.closest(".feed-card");
  if (range && card) seekWithinClip(card, range);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown" || event.key.toLowerCase() === "j") {
    event.preventDefault();
    scrollToClip(activeIndex + 1);
  }
  if (event.key === "ArrowUp" || event.key.toLowerCase() === "k") {
    event.preventDefault();
    scrollToClip(activeIndex - 1);
  }
  if (event.code === "Space") {
    const card = deck.querySelector(`.feed-card[data-index="${activeIndex}"]`);
    if (card) {
      event.preventDefault();
      togglePlay(card);
    }
  }
});

if (levelFilter) {
  levelFilter.addEventListener("change", () => {
    if (activeAudio) activeAudio.pause();
    activeAudio = null;
    renderFeed();
  });
}

async function init() {
  try {
    allClips = await loadFeedData();
  } catch (error) {
    console.error("Failed to load feed data:", error);
    allClips = getDefaultMicroClips().map(normalizeCuratedClip);
  }
  renderFeed();
}

init();
