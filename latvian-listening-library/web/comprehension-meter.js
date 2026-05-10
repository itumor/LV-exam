(function (global) {
  const KNOWN_WORDS_KEY = "lv_listening_known_words";
  const VOCABULARY_KEY = "lv_listening_vocabulary";

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
    "gads", "gada", "gadi", "mēnesis", "nedēļa", "diena", "stunda", "minūte",
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

  function tokenize(text) {
    if (!text || typeof text !== "string") return [];
    return text
      .toLowerCase()
      .replace(/[^\p{L}\p{M}'-]/gu, " ")
      .split(/\s+/)
      .filter((w) => w.length > 0);
  }

  function toLemma(word) {
    return word
      .replace(/ām$/, "āt")
      .replace(/īgs$/, "īgs")
      .replace(/ājs$/, "ājs")
      .replace(/iene$/, "iene")
      .replace(/ējs$/, "ējs")
      .replace(/āna$/, "āt")
      .replace(/āju$/, "āt")
      .replace(/iem$/, "i")
      .replace(/ām$/, "āt")
      .replace(/us$/, "s")
      .replace(/as$/, "a")
      .replace(/es$/, "e")
      .replace(/is$/, "is")
      .replace(/as$/, "as")
      .replace(/ā$/, "āt")
      .replace(/ē$/, "ēt")
      .replace(/ī$/, "īt")
      .replace(/ū$/, "ūt")
      .replace(/šanās$/, "šanās")
      .replace(/šanā$/, "šanā")
      .replace(/šana$/, "šana")
      .replace(/šu$/, "št")
      .replace(/si$/, "s")
      .replace(/ji$/, "jums")
      .replace(/āvām$/, "āt")
      .replace(/ājām$/, "āt")
      .replace(/ojām$/, "ot")
      .replace(/ām$/, "āt")
      .replace(/īt$/, "īt")
      .trim();
  }

  function getKnownWords() {
    try {
      const raw = localStorage.getItem(KNOWN_WORDS_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function saveKnownWord(word, source) {
    const known = getKnownWords();
    const lemma = toLemma(word.toLowerCase());
    known[lemma] = { word: lemma, date: new Date().toISOString(), source: source || "manual" };
    try {
      localStorage.setItem(KNOWN_WORDS_KEY, JSON.stringify(known));
    } catch (e) {
      console.warn("Could not save known word:", e);
    }
    return known;
  }

  function removeKnownWord(word) {
    const known = getKnownWords();
    const lemma = toLemma(word.toLowerCase());
    delete known[lemma];
    try {
      localStorage.setItem(KNOWN_WORDS_KEY, JSON.stringify(known));
    } catch (e) {
      console.warn("Could not update known words:", e);
    }
    return known;
  }

  function getVocabulary() {
    try {
      const raw = localStorage.getItem(VOCABULARY_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
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
    const manual = getKnownWords();
    const vocab = getKnownFromVocab();
    return { ...vocab, ...manual };
  }

  function computeLessonStats(lvText) {
    const tokens = tokenize(lvText);
    const totalWords = tokens.length;
    const knownSet = mergeKnownWords();

    const uniqueTokens = [...new Set(tokens)];
    const uniqueCount = uniqueTokens.length;

    let knownUnique = 0;
    let unknownUnique = [];
    let a2Known = 0;

    for (const word of uniqueTokens) {
      const lemma = toLemma(word);
      if (knownSet[lemma]) {
        knownUnique++;
      } else if (A2_COMMON_WORDS.has(lemma) || A2_COMMON_WORDS.has(word)) {
        a2Known++;
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
    const topUnknown = Object.entries(unknownWordCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([word, count]) => ({ word, count }));

    const comprehensionPct = totalWords > 0 ? Math.round((knownTotal / totalWords) * 100) : 0;

    return {
      totalWords,
      uniqueWords: uniqueCount,
      unknownUniqueWords: unknownUniqueCount,
      estimatedUnknownWords: unknownTotal,
      topUnknownWords: topUnknown,
      comprehensionPct,
      isEstimate: Object.keys(knownSet).length === 0,
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
      const stats = computeLessonStats(item.lv_text);
      return stats.comprehensionPct >= minPct;
    });
  }

  function filterCatalogByLabel(catalog, label) {
    const ranges = {
      easy: [80, 100],
      manageable: [60, 79],
      challenging: [40, 59],
      advanced: [0, 39],
    };
    const [min, max] = ranges[label] || [0, 100];
    return catalog.filter((item) => {
      if (!item.lv_text) return false;
      const stats = computeLessonStats(item.lv_text);
      return stats.comprehensionPct >= min && stats.comprehensionPct <= max;
    });
  }

  const API = {
    tokenize,
    toLemma,
    getKnownWords,
    saveKnownWord,
    removeKnownWord,
    getVocabulary,
    computeLessonStats,
    getComprehensionLabel,
    filterCatalogByComprehension,
    filterCatalogByLabel,
    A2_COMMON_WORDS,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = API;
  } else {
    global.ComprehensionMeter = API;
  }
})(typeof window !== "undefined" ? window : globalThis);
