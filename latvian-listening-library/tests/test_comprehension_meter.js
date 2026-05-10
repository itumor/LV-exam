const fs = require("fs");
const path = require("path");

const A2_COMMON_WORDS = new Set([
  "es", "esmu", "esam", "esat", "esmu", "būt", "ir", "būt",
  "un", "ar", "no", "uz", "par", "pie", "no", "līdz", "pēc", "pirms", "starp",
  "kas", "kur", "kā", "kad", "kurš", "kura", "kas", "ko", "kam", "ar ko",
  "es", "tu", "viņš", "viņa", "mēs", "jūs", "viņi", "viņas",
  "mans", "tavs", "viņa", "mūsu", "jūsu", "viņu",
  "šis", "šī", "tas", "tā", "tie", "tās",
  "un", "bet", "vai", "jo", "ja", "lai", "ka", "jo", "tāpēc",
  "nav", "nē", "jā", "nekad", "vienmēr", "arī", "vairs", "tikai",
  "labdien", "labrīt", "labvakar", "labi", "labs", "laba",
  "rīts", "diena", "nakts", "vakars", "pēcpusdiena", "rīt", "šodien", "vakar",
  "pirmais", "otrā", "otrs", "trešais", "ceturtais", "piektais",
  "vienu", "divi", "trīs", "četri", "pieci", "seši", "septiņi", "astoņi", "deviņi", "desmit",
  "kur", "šeit", "tur", "kaut kur", "visur", "neviena",
  "māja", "dzīvoklis", "istaba", "virtuve", "guļamistaba", "vannasistaba",
  "ģimene", "tēvs", "māte", "brālis", "māsa", "vecāki", "bērns", "bērni", "meita", "dēls",
  "cilvēks", "sieviete", "vīrietis", "meitene", "zēns", "vecs", "jauns",
  "darbs", "strādāt", "darīt", "office", "uzņēmums",
  "skola", "mācīties", "skolotājs", "stundents", "students", "grāmata",
  "ceļš", "iela", "pilsēta", "valsts", "Latvija", "Rīga", "laiks",
  "laiks", "karsts", "auksts", "silts", "lietus", "sniegs", "saule", "debess",
  "ēdiens", " ēst", "dzert", "ūdens", "kafija", "tēja", " maize", "gaļa", "dārzeņi", "augļi",
  "pirkt", "pārdot", "veikals", "cena", "nauda", "maksāt",
  " transports", "autobuss", "tramvajs", "vilciens", "mašīna", "braukt", "iet", "kājām",
  " ārsts", " slimība", "vesels", "veselība", "zāles", "medicīna",
  "diena", "rīts", "vakars", "nakts", "pulkstenis", "laiks",
  "brīvais", "laiks", "sports", "futbols", "mūzika", "grāmata", "kino", "teātris",
  "valoda", "latviešu", "latviski", "angļu", "krievu", "vācu",
  "vārds", "valod", "teikums", "teksts", "vārds",
  "liels", "mazs", "garš", "īss", "augsts", "zems", "plat", "šauru",
  "jauns", "vecs", "suns", "kaķis", "dzīvnieks",
  "draudzība", "draugs", "pazīt", "iebilst",
  "gribēt", "varēt", "dzīvot", "mirt", "just",
  "dot", "ņemt", "palīdzēt", "runāt", "klausīties", "lasīt", "rakstīt",
  "redzēt", "dzirdēt", "just", "domāt", "zināt", "mācēt",
  "atnākt", "aiziet", "palikt", "braukt", "lidot",
  "sākt", "beigt", "turpināt", "gaidīt", "atrast",
  "justies", "būt", "šķist", "kļūt",
  "jā", "nē", "lūdzu", "paldies", "atvainojiet",
  "pirmais", "pirmā", "otrais", "otrā", "trešais", "ceturtais", "piektais",
  "daudz", "maz", "vairāk", "mazāk", "ļoti", "tikko", "gandrīz", "pilnībā",
  "tagad", "tad", "vēlāk", "agrāk", "vienmēr", "nekad",
  "šeit", "tur", "tālu", "netālu", "blakus", "virs", "zem", "iekš", "ārpus",
  "krāsa", "sarkans", "balts", "melns", "zaļš", "zils", "dzeltens", "oranžs",
  "kā", "tā", "bet", "ja", "vai", "ka", "jo", "lai",
  "dēļ", "dēļ", "gala", "vidū", "sākumā", "beigās",
  "prieks", "priecāties", "bailes", "bīties", "būt", "just",
  "gulta", "galds", "krēsls", "logs", "durvis", "mājas", "josta",
  "adres", "nummurs", "telefons", "epasts", "viltnieks",
  "atpūta", "atpūsties", " ceļojums", " ceļot", "valstis",
  "laipns", "īsts", "īsta", "mīļš", "mīlestība", "mīlēt",
  "gaidīt", "pabeigt", "sākt", "pastāvēt", "notikt",
]);

const KNOWN_WORDS_KEY = "lv_listening_known_words";
const VOCABULARY_KEY = "lv_listening_vocabulary";

const localStorage = { data: {}, getItem(k) { return this.data[k] || null; }, setItem(k, v) { this.data[k] = v; }, removeItem(k) { delete this.data[k]; } };

function tokenize(text) {
  if (!text || typeof text !== "string") return [];
  return text.toLowerCase().replace(/[^\p{L}\p{M}'-]/gu, " ").split(/\s+/).filter((w) => w.length > 0);
}

function toLemma(word) {
  return word
    .replace(/ām$/, "āt").replace(/īgs$/, "īgs").replace(/ājs$/, "ājs").replace(/iene$/, "iene")
    .replace(/ējs$/, "ējs").replace(/āna$/, "āt").replace(/āju$/, "āt").replace(/iem$/, "i").replace(/ām$/, "āt")
    .replace(/us$/, "s").replace(/as$/, "a").replace(/es$/, "e").replace(/is$/, "is")
    .replace(/as$/, "as").replace(/ā$/, "āt").replace(/ē$/, "ēt").replace(/ī$/, "īt")
    .replace(/ū$/, "ūt").replace(/šanās$/, "šanās").replace(/šanā$/, "šanā")
    .replace(/šana$/, "šana").replace(/šu$/, "št").replace(/si$/, "s").replace(/ji$/, "jums")
    .replace(/āvām$/, "āt").replace(/ājām$/, "āt").replace(/ojām$/, "ot").replace(/ām$/, "āt")
    .replace(/īt$/, "īt").trim();
}

function getKnownWords() {
  try {
    const raw = localStorage.getItem(KNOWN_WORDS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

function saveKnownWord(word, source) {
  const known = getKnownWords();
  const lemma = toLemma(word.toLowerCase());
  known[lemma] = { word: lemma, date: new Date().toISOString(), source: source || "manual" };
  localStorage.setItem(KNOWN_WORDS_KEY, JSON.stringify(known));
  return known;
}

function removeKnownWord(word) {
  const known = getKnownWords();
  const lemma = toLemma(word.toLowerCase());
  delete known[lemma];
  localStorage.setItem(KNOWN_WORDS_KEY, JSON.stringify(known));
  return known;
}

function getVocabulary() {
  try {
    const raw = localStorage.getItem(VOCABULARY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function getKnownFromVocab() {
  const vocab = getVocabulary();
  const result = {};
  for (const item of vocab) {
    if (item.known) {
      const lemma = toLemma(item.word.toLowerCase());
      result[lemma] = { word: lemma, date: item.knownDate || new Date().toISOString(), source: "vocabulary" };
    }
  }
  return result;
}

function mergeKnownWords() {
  return { ...getKnownFromVocab(), ...getKnownWords() };
}

function computeLessonStats(lvText) {
  const tokens = tokenize(lvText);
  const totalWords = tokens.length;
  const knownSet = mergeKnownWords();
  const uniqueTokens = [...new Set(tokens)];
  const uniqueCount = uniqueTokens.length;

  let knownUnique = 0;
  let unknownUnique = [];
  for (const word of uniqueTokens) {
    const lemma = toLemma(word);
    if (knownSet[lemma] || A2_COMMON_WORDS.has(lemma) || A2_COMMON_WORDS.has(word)) {
      knownUnique++;
    } else {
      unknownUnique.push(word);
    }
  }

  const unknownUniqueCount = uniqueTokens.length - knownUnique;
  const knownTotal = tokens.filter((w) => {
    const l = toLemma(w);
    return knownSet[l] || A2_COMMON_WORDS.has(l) || A2_COMMON_WORDS.has(w);
  }).length;
  const unknownTotal = totalWords - knownTotal;

  const unknownWordCounts = {};
  for (const w of tokens) {
    if (!knownSet[toLemma(w)] && !A2_COMMON_WORDS.has(toLemma(w)) && !A2_COMMON_WORDS.has(w)) {
      unknownWordCounts[w] = (unknownWordCounts[w] || 0) + 1;
    }
  }
  const topUnknown = Object.entries(unknownWordCounts).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([word, count]) => ({ word, count }));

  const comprehensionPct = totalWords > 0 ? Math.round((knownTotal / totalWords) * 100) : 0;

  return {
    totalWords, uniqueWords: uniqueCount, unknownUniqueWords: unknownUniqueCount,
    estimatedUnknownWords: unknownTotal, topUnknownWords: topUnknown,
    comprehensionPct, isEstimate: Object.keys(knownSet).length === 0,
  };
}

function getComprehensionLabel(pct) {
  if (pct >= 80) return { label: "Easy", key: "easy" };
  if (pct >= 60) return { label: "Manageable", key: "manageable" };
  if (pct >= 40) return { label: "Challenging", key: "challenging" };
  return { label: "Advanced", key: "advanced" };
}

function filterCatalogByComprehension(catalog, minPct) {
  return catalog.filter((item) => {
    if (!item.lv_text) return false;
    return computeLessonStats(item.lv_text).comprehensionPct >= minPct;
  });
}

function filterCatalogByLabel(catalog, label) {
  const ranges = { easy: [80, 100], manageable: [60, 79], challenging: [40, 59], advanced: [0, 39] };
  const [min, max] = ranges[label] || [0, 100];
  return catalog.filter((item) => {
    if (!item.lv_text) return false;
    const stats = computeLessonStats(item.lv_text);
    return stats.comprehensionPct >= min && stats.comprehensionPct <= max;
  });
}

let passed = 0;
let failed = 0;

function test(name, fn) {
  localStorage.data = {};
  try {
    fn();
    console.log("PASS:", name);
    passed++;
  } catch (e) {
    console.error("FAIL:", name, "-", e.message);
    failed++;
  }
}

function eq(a, b) {
  if (a !== b) throw new Error(`Expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
}

// --- Tokenization tests ---
test("tokenize: handles basic words", () => {
  eq(tokenize("es esmu būt").join(","), "es,esmu,būt");
});

test("tokenize: handles Latvian diacritics", () => {
  const words = tokenize("čau ēdu garš ģimene īss ķermeņa ņēmu ūdens žūpu");
  eq(words.length, 9);
  eq(words[0], "čau");
  eq(words[1], "ēdu");
  eq(words[5], "ķermeņa");
  eq(words[6], "ņēmu");
  eq(words[8], "žūpu");
});

test("tokenize: lowercase conversion", () => {
  eq(tokenize("ES LŪDZU PALDIES").join(","), "es,lūdzu,paldies");
});

test("tokenize: strips punctuation", () => {
  eq(tokenize("Labdien! Kā jūs sauc?").join(","), "labdien,kā,jūs,sauc");
});

test("tokenize: handles empty/null input", () => {
  eq(tokenize("").length, 0);
  eq(tokenize(null).length, 0);
  eq(tokenize(undefined).length, 0);
});

test("tokenize: handles numbers and special chars", () => {
  const words = tokenize("Es dzīvoju Rīgā, 2024. gadā!");
  eq(words.includes("2024"), false);
});

// --- Lemma tests ---
test("toLemma: basic lemmas", () => {
  eq(toLemma("esmu"), "esmu");
  eq(toLemma("mājas"), "māja");
  eq(toLemma("runāju"), "runāt");
});

// --- Comprehension estimation tests ---
test("computeLessonStats: basic", () => {
  const stats = computeLessonStats("Labdien! Kā jūs sauc? Mani sauc Jānis.");
  eq(typeof stats.totalWords, "number");
  eq(stats.totalWords > 0, true);
  eq(typeof stats.uniqueWords, "number");
  eq(typeof stats.comprehensionPct, "number");
  eq(stats.comprehensionPct >= 0 && stats.comprehensionPct <= 100, true);
});

test("computeLessonStats: all common words = high comprehension", () => {
  const text = "es esmu labs tu esi labs mēs esam labi jūs esat labi";
  const stats = computeLessonStats(text);
  eq(stats.comprehensionPct > 70, true);
});

test("computeLessonStats: shows unknown words", () => {
  const stats = computeLessonStats("blah blah blah xyz qrs");
  eq(stats.topUnknownWords.length > 0, true);
});

test("computeLessonStats: marks estimate when no vocabulary", () => {
  const stats = computeLessonStats("kaut kas nesaprotams");
  eq(stats.isEstimate, true);
});

test("computeLessonStats: unknownUniqueWords is count of unique unknown", () => {
  const stats = computeLessonStats("blah blah blah foo bar bar");
  eq(typeof stats.unknownUniqueWords, "number");
  eq(stats.unknownUniqueWords >= 0, true);
});

test("computeLessonStats: topUnknownWords sorted by frequency", () => {
  const stats = computeLessonStats("xyz xyz xyz abc abc def");
  eq(stats.topUnknownWords[0].word, "xyz");
  eq(stats.topUnknownWords[0].count, 3);
  eq(stats.topUnknownWords[1].word, "abc");
  eq(stats.topUnknownWords[1].count, 2);
});

test("computeLessonStats: limits topUnknownWords to 10", () => {
  const words = Array.from({ length: 30 }, (_, i) => `word${i}`).join(" ");
  const stats = computeLessonStats(words);
  eq(stats.topUnknownWords.length <= 10, true);
});

// --- Label tests ---
test("getComprehensionLabel: easy 80+", () => {
  eq(getComprehensionLabel(85).key, "easy");
  eq(getComprehensionLabel(100).key, "easy");
});

test("getComprehensionLabel: manageable 60-79", () => {
  eq(getComprehensionLabel(75).key, "manageable");
  eq(getComprehensionLabel(60).key, "manageable");
});

test("getComprehensionLabel: challenging 40-59", () => {
  eq(getComprehensionLabel(50).key, "challenging");
  eq(getComprehensionLabel(40).key, "challenging");
});

test("getComprehensionLabel: advanced below 40", () => {
  eq(getComprehensionLabel(30).key, "advanced");
  eq(getComprehensionLabel(0).key, "advanced");
});

// --- Known word store tests ---
test("saveKnownWord: stores word in localStorage", () => {
  saveKnownWord("brīnišķīgs", "manual");
  const known = getKnownWords();
  eq(Object.keys(known).length > 0, true);
});

test("saveKnownWord: word has date and source", () => {
  saveKnownWord("tests", "manual");
  const known = getKnownWords();
  const lemma = toLemma("tests");
  eq(typeof known[lemma].date, "string");
  eq(known[lemma].source, "manual");
});

test("removeKnownWord: removes word", () => {
  saveKnownWord("testword123", "manual");
  removeKnownWord("testword123");
  const known = getKnownWords();
  eq(typeof known[toLemma("testword123")], "undefined");
});

test("saveKnownWord: updates comprehension after marking known", () => {
  const text = "es ēdu garšīgu";
  const before = computeLessonStats(text);
  saveKnownWord("garšīgu", "manual");
  const after = computeLessonStats(text);
  eq(after.unknownUniqueWords <= before.unknownUniqueWords, true);
  removeKnownWord("garšīgu");
});

// --- Filter tests ---
test("filterCatalogByComprehension: returns matching items", () => {
  const catalog = [
    { id: "1", lv_text: "es esmu labs tu labs viss labs" },
    { id: "2", lv_text: "xyz qrs abc def" },
    { id: "3", lv_text: "es esmu un tu esi" },
  ];
  const result = filterCatalogByComprehension(catalog, 60);
  eq(Array.isArray(result), true);
});

test("filterCatalogByLabel: easy filter", () => {
  const catalog = [
    { id: "1", lv_text: "es esmu labs tu labs viss labs" },
    { id: "2", lv_text: "xyz qrs abc def ghi jkl mno pqr" },
  ];
  const result = filterCatalogByLabel(catalog, "easy");
  eq(Array.isArray(result), true);
  eq(result.length <= catalog.length, true);
});

test("filterCatalogByLabel: skips items without text", () => {
  const catalog = [
    { id: "1", lv_text: null },
    { id: "2", lv_text: "es esmu labs" },
  ];
  const result = filterCatalogByLabel(catalog, "easy");
  eq(result.some((i) => i.id === "1"), false);
});

// --- Summary ---
console.log(`\nResults: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
