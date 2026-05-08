(function () {
  "use strict";

  const CACHE_PREFIX = "ai-transcript-cache-v1";
  const CACHE_VERSION = "1.0";

  function getCacheKey(sentence, lessonId, explanationVersion) {
    const hash = simpleHash(sentence + lessonId + explanationVersion);
    return `${CACHE_PREFIX}-${lessonId}-${hash}`;
  }

  function simpleHash(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) {
      h = ((h << 5) - h + str.charCodeAt(i)) | 0;
    }
    return Math.abs(h).toString(36);
  }

  function getFromCache(key) {
    try {
      const cached = localStorage.getItem(key);
      if (cached) {
        const data = JSON.parse(cached);
        if (data.timestamp && Date.now() - data.timestamp < 7 * 24 * 60 * 60 * 1000) {
          return data.explanation;
        }
        localStorage.removeItem(key);
      }
    } catch (e) {
      console.warn("Cache read error:", e);
    }
    return null;
  }

  function setToCache(key, explanation) {
    try {
      localStorage.setItem(
        key,
        JSON.stringify({
          explanation,
          timestamp: Date.now(),
        })
      );
    } catch (e) {
      console.warn("Cache write error:", e);
    }
  }

  function safeLog(type, data) {
    const safeData = { ...data };
    delete safeData.userAccountDetails;
    console.log(`[AI Transcript] ${type}`, safeData);
  }

  class MockAIProvider {
    constructor() {
      this.vocabularyDatabase = {
        prieks: { lemma: "prieks", pos: "noun", case: "nominative", meaning: "joy, happiness", example: "Man ir prieks." },
        iepazīties: { lemma: "iepazīties", pos: "verb", infinitive: "iepazīties", meaning: "to meet, get acquainted", example: "Prieks iepazīties!" },
        labs: { lemma: "labs", pos: "adjective", meaning: "good", example: "Tas ir labs." },
        rīt: { lemma: "rīts", pos: "noun", case: "nominative", meaning: "morning", example: "Šorīt ir labs rīts." },
        diena: { lemma: "diena", pos: "noun", case: "nominative", meaning: "day", example: "Šodiena ir skaista diena." },
        sveiks: { lemma: "sveiks", pos: "interjection", meaning: "hello (informal)", example: "Sveiks, kā tev iet?" },
        sveika: { lemma: "sveiks", pos: "interjection", meaning: "hello (informal, female)", example: "Sveika, kā tev iet?" },
        labdien: { lemma: "labdien", pos: "interjection", meaning: "good day, hello", example: "Labdien! Kā jums klājas?" },
        paldies: { lemma: "paldies", pos: "interjection", meaning: "thank you", example: "Paldies par palīdzību." },
        lūdzu: { lemma: "lūdzu", pos: "interjection", meaning: "please / you're welcome", example: "Lūdzu, varu palīdzēt?" },
        jā: { lemma: "jā", pos: "adverb", meaning: "yes", example: "Jā, es gribu." },
        nē: { lemma: "nē", pos: "adverb", meaning: "no", example: "Nē, paldies." },
        es: { lemma: "es", pos: "pronoun", meaning: "I", example: "Es esmu students." },
        tu: { lemma: "tu", pos: "pronoun", meaning: "you (informal)", example: "Tu runā latviski." },
        viņš: { lemma: "viņš", pos: "pronoun", meaning: "he", example: "Viņš mācās." },
        viņa: { lemma: "viņa", pos: "pronoun", meaning: "she", example: "Viņa runā." },
        mēs: { lemma: "mēs", pos: "pronoun", meaning: "we", example: "Mēs esam draugi." },
        jums: { lemma: "jūs", pos: "pronoun", meaning: "you (formal/plural)", example: "Jums ir skaists." },
        viņi: { lemma: "viņi", pos: "pronoun", meaning: "they (male)", example: "Viņi mācās." },
        viņas: { lemma: "viņas", pos: "pronoun", meaning: "they (female)", example: "Viņas runā." },
        būt: { lemma: "būt", pos: "verb", infinitive: "būt", meaning: "to be", example: "Es gribu būt." },
        ir: { lemma: "būt", pos: "verb", form: "present 3rd singular", meaning: "is", example: "Viņš ir labs." },
        nav: { lemma: "būt", pos: "verb", form: "present 3rd singular negative", meaning: "is not", example: "Tas nav mans." },
        runāt: { lemma: "runāt", pos: "verb", infinitive: "runāt", meaning: "to speak, talk", example: "Es runāju latviešu valodā." },
        mācīties: { lemma: "mācīties", pos: "verb", infinitive: "mācīties", meaning: "to study, learn", example: "Es mācos valodu." },
        dzīvot: { lemma: "dzīvot", pos: "verb", infinitive: "dzīvot", meaning: "to live", example: "Es dzīvoju Rīgā." },
        strādāt: { lemma: "strādāt", pos: "verb", infinitive: "strādāt", meaning: "to work", example: "Viņš strādā bankā." },
        nākt: { lemma: "nākt", pos: "verb", infinitive: "nākt", meaning: "to come", example: "Viņš nāk uzskolā." },
        iet: { lemma: "iet", pos: "verb", infinitive: "iet", meaning: "to go", example: "Es ieju veikalā." },
        redzēt: { lemma: "redzēt", pos: "verb", infinitive: "redzēt", meaning: "to see", example: "Es redzu jūs." },
        dzirdēt: { lemma: "dzirdēt", pos: "verb", infinitive: "dzirdēt", meaning: "to hear", example: "Es dzirdu mūziku." },
        saprast: { lemma: "saprast", pos: "verb", infinitive: "saprast", meaning: "to understand", example: "Es saprotu." },
        gribēt: { lemma: "gribēt", pos: "verb", infinitive: "gribēt", meaning: "to want", example: "Es gribu ūdeni." },
        varēt: { lemma: "varēt", pos: "verb", infinitive: "varēt", meaning: "to be able, can", example: "Es varu palīdzēt." },
        zināt: { lemma: "zināt", pos: "verb", infinitive: "zināt", meaning: "to know", example: "Es zinu atbildi." },
        domāt: { lemma: "domāt", pos: "verb", infinitive: "domāt", meaning: "to think", example: "Es domāju, ka tā ir." },
        just: { lemma: "just", pos: "verb", infinitive: "just", meaning: "to feel", example: "Es jūtos labi." },
        palīdzēt: { lemma: "palīdzēt", pos: "verb", infinitive: "palīdzēt", meaning: "to help", example: "Vai jūs varat palīdzēt?" },
        māja: { lemma: "māja", pos: "noun", case: "nominative", meaning: "house, home", example: "Mana māja ir liela." },
        ģimene: { lemma: "ģimene", pos: "noun", case: "nominative", meaning: "family", example: "Mana ģimene ir maza." },
        draugs: { lemma: "draugs", pos: "noun", case: "nominative", meaning: "friend (male)", example: "Viņš ir mans draugs." },
        draudzene: { lemma: "draugs", pos: "noun", case: "nominative", meaning: "friend (female)", example: "Viņa ir mana draudzene." },
        pilsēta: { lemma: "pilsēta", pos: "noun", case: "nominative", meaning: "city", example: "Rīga ir skaista pilsēta." },
        valsts: { lemma: "valsts", pos: "noun", case: "nominative", meaning: "country, state", example: "Latvija ir mana valsts." },
        valoda: { lemma: "valoda", pos: "noun", case: "nominative", meaning: "language", example: "Latviešu valoda ir skaista." },
        ūdens: { lemma: "ūdens", pos: "noun", case: "nominative", meaning: "water", example: "Man vajag ūdeni." },
        maize: { lemma: "maize", pos: "noun", case: "nominative", meaning: "bread", example: "Es gribu maizi." },
        ēst: { lemma: "ēst", pos: "verb", infinitive: "ēst", meaning: "to eat", example: "Es ēdu ābolu." },
        dzert: { lemma: "dzert", pos: "verb", infinitive: "dzert", meaning: "to drink", example: "Es dzeru kafiju." },
        gulēt: { lemma: "gulēt", pos: "verb", infinitive: "gulēt", meaning: "to sleep", example: "Es gulu vakarā." },
        celies: { lemma: "celies", pos: "verb", form: "imperative", meaning: "get up", example: "Celies!" },
        ej: { lemma: "iet", pos: "verb", form: "imperative", meaning: "go", example: "Ej uz veikalu!" },
        nāc: { lemma: "nākt", pos: "verb", form: "imperative", meaning: "come", example: "Nāc šurp!" },
      };
    }

    async explainSentence(sentence, context, simpleMode) {
      await this.simulateLatency();

      const words = sentence.toLowerCase().split(/\s+/).filter(w => w.length > 1);
      const vocab = [];

      for (const word of words) {
        const cleanWord = word.replace(/[.,!?;:()]/g, "");
        if (this.vocabularyDatabase[cleanWord]) {
          vocab.push({
            word: cleanWord,
            ...this.vocabularyDatabase[cleanWord]
          });
        }
      }

      const literalWords = [];
      const word meanings = {
        prieks: "joy", iepazities: "meet", labs: "good", rit: "morning",
        diena: "day", sveiks: "hello", labdien: "good-day", paldies: "thanks",
        lūdzu: "please", jā: "yes", nē: "no", es: "I", tu: "you", viņš: "he",
        viņa: "she", mēs: "we", jums: "you-formal", viņi: "they-m",
        viņas: "they-f", būt: "to-be", ir: "is", nav: "is-not",
        runāt: "to-speak", mācīties: "to-study", dzīvot: "to-live",
        strādāt: "to-work", nākt: "to-come", iet: "to-go"
      };
      
      for (const word of words) {
        const clean = word.replace(/[.,!?;:'"]/g, "");
        literalWords.push(meanings[clean] || clean);
      }

      const grammarNotes = [];
      if (sentence.includes(" ir ") || sentence.includes("nav ")) {
        grammarNotes.push("The verb 'ir' (to be) is often omitted in present tense. 'Ir' = is, 'nav' = is not");
      }
      if (sentence.includes("es ") || sentence.includes("Tu ") || sentence.includes(" tu ")) {
        grammarNotes.push("Latvian pronouns often drop the subject when the verb ending makes it clear");
      }
      if (/[āēīūšģķļžčņ]$/.test(sentence.trim())) {
        grammarNotes.push("Many Latvian words end with long vowels - notice the ā, ē, ī, ū marks");
      }

      return {
        naturalTranslation: this.generateNaturalTranslation(sentence, simpleMode),
        literalTranslation: literalWords.join(" "),
        vocabulary: vocab.slice(0, 8),
        grammarNotes,
        verbForms: this.extractVerbForms(sentence),
        caseNotes: this.extractCaseNotes(sentence),
        whyThisForm: this.explainWhyForm(sentence),
        simpleMode
      };
    }

    async explainWord(word, sentence) {
      await this.simulateLatency();
      
      const cleanWord = word.toLowerCase().replace(/[.,!?;:()]/g, "");
      const vocabEntry = this.vocabularyDatabase[cleanWord];
      
      if (vocabEntry) {
        return {
          word: cleanWord,
          lemma: vocabEntry.lemma || cleanWord,
          partOfSpeech: vocabEntry.pos,
          caseOrTense: vocabEntry.case || vocabEntry.form || null,
          simpleExample: vocabEntry.example,
          meaning: vocabEntry.meaning,
          inContext: sentence
        };
      }

      return {
        word: cleanWord,
        lemma: cleanWord,
        partOfSpeech: "unknown",
        caseOrTense: null,
        simpleExample: null,
        meaning: "Word not in database - try a common word",
        inContext: sentence
      };
    }

    generateNaturalTranslation(sentence, simpleMode) {
      const translations = {
        "prieks iepazīties": "Nice to meet you",
        "labdien": "Good day / Hello",
        "sveiks": "Hello (informal)",
        "kā tev iet": "How are you?",
        "kā jums klājas": "How are you? (formal)",
        "paldies": "Thank you",
        "lūdzu": "Please / You're welcome",
        "man ir labs rīts": "I have a good morning",
        "kā tev klājas": "How are you doing?",
        "visu labu": "All the best / Goodbye"
      };

      const lower = sentence.toLowerCase().trim();
      if (translations[lower]) {
        return translations[lower];
      }

      if (simpleMode) {
        return `[Latvian: ${sentence}]`;
      }
      
      return "A2-level Latvian sentence. Practice listening to understand the context.";
    }

    extractVerbForms(sentence) {
      const forms = [];
      const verbs = {
        "esmu": { verb: "būt", form: "1st person singular present", meaning: "I am" },
        "esi": { verb: "būt", form: "2nd person singular present", meaning: "you are" },
        "ir": { verb: "būt", form: "3rd person singular present", meaning: "he/she/it is" },
        "esam": { verb: "būt", form: "1st person plural present", meaning: "we are" },
        "esat": { verb: "būt", form: "2nd person plural present", meaning: "you all are" },
        "ir": { verb: "būt", form: "3rd person plural present", meaning: "they are" },
        "biju": { verb: "būt", form: "1st person singular past", meaning: "I was" },
        "biji": { verb: "būt", form: "2nd person singular past", meaning: "you were" },
        "bija": { verb: "būt", form: "3rd person singular past", meaning: "he/she/it was" },
        "bijām": { verb: "būt", form: "1st person plural past", meaning: "we were" },
        "bijāt": { verb: "būt", form: "2nd person plural past", meaning: "you all were" },
        "bija": { verb: "būt", form: "3rd person plural past", meaning: "they were" },
      };

      const words = sentence.split(/\s+/);
      for (const word of words) {
        const clean = word.toLowerCase().replace(/[.,!?]/g, "");
        if (verbs[clean]) {
          forms.push(verbs[clean]);
        }
      }
      return forms;
    }

    extractCaseNotes(sentence) {
      const notes = [];
      
      if (sentence.includes("man") || sentence.includes("tav") || sentence.includes("viņ") || sentence.includes("mūsu")) {
        notes.push({
          case: "genitive (possessive)",
          explanation: "Words like man, tava, viņa show possession - 'my', 'your', 'his/her'",
          example: "mana māja = my house (literally 'of me house')"
        });
      }
      
      if (sentence.includes(" - ") || sentence.includes("uz")) {
        notes.push({
          case: "accusative (direction)",
          explanation: "Prepositions like uz (to/towards) often take accusative case",
          example: "uz skolu = to school"
        });
      }

      if (sentence.includes("ar") || sentence.includes("kopā")) {
        notes.push({
          case: "instrumental (with)",
          explanation: "The word ar (with) uses instrumental case",
          example: "ar draugu = with a friend"
        });
      }

      return notes;
    }

    explainWhyForm(sentence) {
      const explanations = [];

      if (sentence.includes("nav")) {
        explanations.push({
          phrase: "nav",
          explanation: "Nav is the negated form of 'ir' (to be). In Latvian, negation is a single word, not an auxiliary.",
          pattern: "subject + nav + predicate (NOT: subject + ne + verb)"
        });
      }

      if (sentence.endsWith("s") || sentence.endsWith("š")) {
        explanations.push({
          phrase: "verb ending -s/-š",
          explanation: "Many 3rd person singular verbs end in -s or -š. This is different from English where we add -s/-es.",
          pattern: "viņš runā = he speaks (NOT: he speak)"
        });
      }

      if (explanations.length === 0) {
        explanations.push({
          phrase: "general",
          explanation: "This sentence follows standard A2-level grammar patterns for everyday Latvian.",
          pattern: "A2 level uses simple present, basic questions, and common phrases"
        });
      }

      return explanations;
    }

    async extractVocabulary(text, limit = 10) {
      await this.simulateLatency();
      
      const words = text.toLowerCase().split(/\s+/).filter(w => w.length > 2);
      const vocab = [];

      for (const word of words) {
        const cleanWord = word.replace(/[.,!?;:()]/g, "");
        if (this.vocabularyDatabase[cleanWord] && !vocab.find(v => v.word === cleanWord)) {
          vocab.push({
            word: cleanWord,
            ...this.vocabularyDatabase[cleanWord]
          });
          if (vocab.length >= limit) break;
        }
      }

      return vocab;
    }

    async explainGrammarPoint(sentence, selectedWord) {
      return this.explainWord(selectedWord, sentence);
    }

    simulateLatency() {
      return new Promise(resolve => setTimeout(resolve, 300 + Math.random() * 200));
    }
  }

  class RealAIProvider {
    constructor(config) {
      this.apiUrl = config.apiUrl || "/api/ai-explain";
      this.apiKey = config.apiKey;
    }

    async explainSentence(sentence, context, simpleMode) {
      const response = await fetch(this.apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {})
        },
        body: JSON.stringify({
          sentence,
          context,
          simpleMode,
          mode: "sentence"
        })
      });

      if (!response.ok) {
        throw new Error(`AI request failed: ${response.status}`);
      }

      return response.json();
    }

    async explainWord(word, sentence) {
      const response = await fetch(this.apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {})
        },
        body: JSON.stringify({
          word,
          sentence,
          mode: "word"
        })
      });

      if (!response.ok) {
        throw new Error(`AI request failed: ${response.status}`);
      }

      return response.json();
    }

    async extractVocabulary(text, limit) {
      const response = await fetch(this.apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {})
        },
        body: JSON.stringify({
          text,
          limit,
          mode: "vocabulary"
        })
      });

      if (!response.ok) {
        throw new Error(`AI request failed: ${response.status}`);
      }

      return response.json();
    }

    async explainGrammarPoint(sentence, selectedWord) {
      return this.explainWord(selectedWord, sentence);
    }
  }

  class AIExplanationService {
    constructor() {
      this.provider = this.createProvider();
      this.currentLessonId = null;
      this.explanationMode = "simple";
      this.cache = true;
    }

    createProvider() {
      const envAIUrl = typeof window !== "undefined" ? window.ENV_AI_API_URL : null;
      const envAPIKey = typeof window !== "undefined" ? window.ENV_AI_API_KEY : null;

      if (envAIUrl) {
        safeLog("info", { mode: "real-backend", url: envAIUrl });
        return new RealAIProvider({ apiUrl: envAIUrl, apiKey: envAPIKey });
      }

      safeLog("info", { mode: "mock-backend" });
      return new MockAIProvider();
    }

    async explainSentence(sentence, context = {}) {
      const lessonId = context.lessonId || this.currentLessonId || "default";
      const cacheKey = getCacheKey(sentence, lessonId, CACHE_VERSION);

      if (this.cache) {
        const cached = getFromCache(cacheKey);
        if (cached) {
          safeLog("cache-hit", { sentence: sentence.substring(0, 30), lessonId });
          return cached;
        }
      }

      safeLog("request", { sentence: sentence.substring(0, 50), lessonId });

      try {
        const result = await this.provider.explainSentence(
          sentence,
          context,
          this.explanationMode === "simple"
        );

        if (this.cache) {
          setToCache(cacheKey, result);
        }

        return result;
      } catch (error) {
        safeLog("error", { error: error.message });
        throw error;
      }
    }

    async explainWord(word, sentence) {
      safeLog("word-request", { word, sentence: sentence.substring(0, 30) });

      try {
        return await this.provider.explainWord(word, sentence);
      } catch (error) {
        safeLog("error", { error: error.message });
        throw error;
      }
    }

    async extractVocabulary(text, limit = 10) {
      try {
        return await this.provider.extractVocabulary(text, limit);
      } catch (error) {
        safeLog("error", { error: error.message });
        throw error;
      }
    }

    async explainGrammarPoint(sentence, selectedWord) {
      try {
        return await this.provider.explainGrammarPoint(sentence, currentWord);
      } catch (error) {
        safeLog("error", { error: error.message });
        throw error;
      }
    }

    setLessonId(id) {
      this.currentLessonId = id;
    }

    setExplanationMode(mode) {
      this.explanationMode = mode === "detailed" ? "detailed" : "simple";
    }

    toggleCaching(enabled) {
      this.cache = enabled;
    }
  }

  if (typeof window !== "undefined") {
    window.AIExplanationService = AIExplanationService;
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { AIExplanationService, MockAIProvider, RealAIProvider };
  }
})();