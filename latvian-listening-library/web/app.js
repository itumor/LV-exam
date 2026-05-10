(function () {
  // ---------------------------------------------------------------------------
  // CommunityService — community features (questions, comments, translations)
  // ---------------------------------------------------------------------------
  var CommunityService = (function () {
  var STORAGE_KEY = "lv_listening_community";
  var REPORTED_KEY = "lv_listening_reported";

  function getEntries() {
    try {
      var data = localStorage.getItem(STORAGE_KEY);
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
      var data = localStorage.getItem(REPORTED_KEY);
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
      var entries = getEntries().filter(
        function(e) { return e.lessonId === lessonId && e.type === type; }
      );
      var reported = getReported();
      var filtered = entries.filter(function(e) { return reported.indexOf(e.id) === -1; });
      if (sort === "helpful") {
        filtered.sort(function(a, b) { return (b.helpfulVotes || 0) - (a.helpfulVotes || 0); });
      } else {
        filtered.sort(function(a, b) { return new Date(b.createdAt) - new Date(a.createdAt); });
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
=======
(function () {
  // ---------------------------------------------------------------------------
  // ThemeManager — apply theme before any paint
  // ---------------------------------------------------------------------------
  var ThemeManager = {
    apply: function (theme) {
      document.documentElement.setAttribute('data-theme', theme);
      var btn = document.getElementById('theme-toggle');
      if (btn) {
        var result = toggleTheme(theme);
        btn.setAttribute('aria-label', result.ariaLabel);
      }
    },
    toggle: function () {
      var current = document.documentElement.getAttribute('data-theme') || 'light';
      var result = toggleTheme(current);
      ThemeManager.apply(result.theme);
      try { localStorage.setItem('theme', result.theme); } catch (e) {}
    },
    init: function () {
      var stored;
      try { stored = localStorage.getItem('theme'); } catch (e) {}
      if (stored === 'dark' || stored === 'light') {
        ThemeManager.apply(stored);
      }
    }
  };

  // Apply theme synchronously before any DOM manipulation / paint
  ThemeManager.init();

  // ---------------------------------------------------------------------------
  // Vocabulary Flashcard System
  // ---------------------------------------------------------------------------
  var STORAGE_KEY = "latvian_flashcards";
  var STOPWORDS = new Set(["un", "un", "bet", "vai", "ir", "bija", "būs", "ir", "nav", "būt", "ka", "lai", "kas", "kur", "kad", "kā", "jo", "līdz", "par", "pēc", "priekš", "aiz", "uz", "no", "pie", "pa", "pāri", "starp", "ar", "sā", "tā", "arī", "vēl", "jau", "gan", " gan", "tikai", "tomēr", "tad", "ja", "kā", "lai", "lai", "būtu", "var", "varētu", "vajag", "jā", "ne", "nē", "nekad", "nekā", "neko", "nevis", "neviņ", "neviens", "negaidīt", "nestrādā", "nestāv", "nesēž", "neliek", "nemarš", "nebrauc", "neiet", "nav", "nu", "jā", "protams", "žēl", "dieva", "dievs", "žēl", "noteikti", "noteikti", "acīm", "protams", "esot", "tiktu", "tiek", "tik", "tikai", "it"]);

  var VOCAB_DICTIONARY = {
    "labs": { en: "good", grammar: "adj" },
    "slikts": { en: "bad", grammar: "adj" },
    "liels": { en: "big, large", grammar: "adj" },
    "mazs": { en: "small", grammar: "adj" },
    "jauns": { en: "new", grammar: "adj" },
    "vecs": { en: "old", grammar: "adj" },
    "skaists": { en: "beautiful", grammar: "adj" },
    "garš": { en: "long", grammar: "adj" },
    "īss": { en: "short", grammar: "adj" },
    "augsts": { en: "tall, high", grammar: "adj" },
    "zems": { en: "low", grammar: "adj" },
    "balss": { en: "voice", grammar: "noun" },
  "cils": { en: "dear", grammar: "adj" },
  "mīļš": { en: "beloved, dear", grammar: "adj" },
  "dārgs": { en: "expensive", grammar: "adj" },
  "lēts": { en: "cheap", grammar: "adj" },
  "vesels": { en: "healthy", grammar: "adj" },
  "slims": { en: "sick", grammar: "adj" },
  "gatavs": { en: "ready", grammar: "adj" },
  "gatava": { en: "ready", grammar: "adj" },
  "gatavi": { en: "ready", grammar: "adj" },
  "pabeigts": { en: "finished", grammar: "adj" },
  "skaidrs": { en: "clear", grammar: "adj" },
  "jaunā": { en: "new", grammar: "adj" },
  "jaunie": { en: "new", grammar: "adj" },
  "jauns": { en: "new", grammar: "adj" },
  "veca": { en: "old", grammar: "adj" },
  "vecs": { en: "old", grammar: "adj" },
  "name": { en: "name", grammar: "noun" },
  "vārds": { en: "first name", grammar: "noun" },
  "uzvārds": { en: "surname", grammar: "noun" },
  "valsts": { en: "state, country", grammar: "noun" },
  "pilsēta": { en: "city", grammar: "noun" },
  "iela": { en: "street", grammar: "noun" },
  "māja": { en: "house", grammar: "noun" },
  "dzīvoklis": { en: "apartment", grammar: "noun" },
  "logs": { en: "window", grammar: "noun" },
  "durvis": { en: "door", grammar: "noun" },
  "istaba": { en: "room", grammar: "noun" },
  "virtuve": { en: "kitchen", grammar: "noun" },
  "guļamistaba": { en: "bedroom", grammar: "noun" },
  "vannasistaba": { en: "bathroom", grammar: "noun" },
  "balto": { en: "white", grammar: "adj" },
  "melns": { en: "black", grammar: "adj" },
  "sarkans": { en: "red", grammar: "adj" },
  "zils": { en: "blue", grammar: "adj" },
  "zaļš": { en: "green", grammar: "adj" },
  "dzeltens": { en: "yellow", grammar: "adj" },
  "oranžs": { en: "orange", grammar: "adj" },
  "violets": { en: "purple", grammar: "adj" },
  "pelēks": { en: "gray", grammar: "adj" },
  "brūns": { en: "brown", grammar: "adj" },
  "cilvēks": { en: "person", grammar: "noun" },
  "vīrietis": { en: "man", grammar: "noun" },
  "sieviete": { en: "woman", grammar: "noun" },
  "bērns": { en: "child", grammar: "noun" },
  "bērni": { en: "children", grammar: "noun" },
  "zēns": { en: "boy", grammar: "noun" },
  "meitene": { en: "girl", grammar: "noun" },
  "tēvs": { en: "father", grammar: "noun" },
  "māte": { en: "mother", grammar: "noun" },
  "vectēvs": { en: "grandfather", grammar: "noun" },
  "vecmāte": { en: "grandmother", grammar: "noun" },
  "mazdēls": { en: "grandson", grammar: "noun" },
  "mazmeita": { en: "granddaughter", grammar: "noun" },
  "brālis": { en: "brother", grammar: "noun" },
  "māsa": { en: "sister", grammar: "noun" },
  "dēls": { en: "son", grammar: "noun" },
  "meita": { en: "daughter", grammar: "noun" },
  "ģimene": { en: "family", grammar: "noun" },
  "laulātais": { en: "spouse", grammar: "noun" },
  "vīrs": { en: "husband", grammar: "noun" },
  "sieva": { en: "wife", grammar: "noun" },
  " draugs": { en: "friend", grammar: "noun" },
  "kolega": { en: "colleague", grammar: "noun" },
  "kaimiņš": { en: "neighbor", grammar: "noun" },
  "skolotājs": { en: "teacher (male)", grammar: "noun" },
  "skolotāja": { en: "teacher (female)", grammar: "noun" },
  "ārsts": { en: "doctor", grammar: "noun" },
  "medmāsa": { en: "nurse", grammar: "noun" },
  "farmaceits": { en: "pharmacist", grammar: "noun" },
  "pārdevējs": { en: "seller, shop assistant", grammar: "noun" },
  "autovadītājs": { en: "driver", grammar: "noun" },
  "esmu": { en: "I am", grammar: "verb" },
  "esi": { en: "you are", grammar: "verb" },
  "ir": { en: "is/are", grammar: "verb" },
  "biju": { en: "I was", grammar: "verb" },
  "biji": { en: "you were", grammar: "verb" },
  "bija": { en: "was/were", grammar: "verb" },
  "būšu": { en: "I will be", grammar: "verb" },
  "būsi": { en: "you will be", grammar: "verb" },
  "būs": { en: "will be", grammar: "verb" },
  "būt": { en: "to be", grammar: "verb" },
  "darīt": { en: "to do", grammar: "verb" },
  "daru": { en: "I do", grammar: "verb" },
  "dari": { en: "do!", grammar: "verb" },
  "dzīvot": { en: "to live", grammar: "verb" },
  "dzīvoju": { en: "I live", grammar: "verb" },
  "dzīvo": { en: "live!", grammar: "verb" },
  "strādāt": { en: "to work", grammar: "verb" },
  "strādāju": { en: "I work", grammar: "verb" },
  "strādā": { en: "work!", grammar: "verb" },
  "mācīties": { en: "to study", grammar: "verb" },
  "mācos": { en: "I study", grammar: "verb" },
  "mācīties": { en: "study!", grammar: "verb" },
  "gribēt": { en: "to want", grammar: "verb" },
  "gribu": { en: "I want", grammar: "verb" },
  "grib": { en: "want!", grammar: "verb" },
  "varēt": { en: "can, to be able", grammar: "verb" },
  "varu": { en: "I can", grammar: "verb" },
  "var": { en: "can!", grammar: "verb" },
  "prast": { en: "to know how", grammar: "verb" },
  "protu": { en: "I know how", grammar: "verb" },
  "prot": { en: "know how!", grammar: "verb" },
  "zināt": { en: "to know", grammar: "verb" },
  "zinu": { en: "I know", grammar: "verb" },
  "zina": { en: "know!", grammar: "verb" },
  "domāt": { en: "to think", grammar: "verb" },
  "domāju": { en: "I think", grammar: "verb" },
  "domā": { en: "think!", grammar: "verb" },
  "redzēt": { en: "to see", grammar: "verb" },
  "redzu": { en: "I see", grammar: "verb" },
  "redz": { en: "see!", grammar: "verb" },
  "dzirdēt": { en: "to hear", grammar: "verb" },
  "dzirdu": { en: "I hear", grammar: "verb" },
  "dzird": { en: "hear!", grammar: "verb" },
  "teikt": { en: "to say", grammar: "verb" },
  "saku": { en: "I say", grammar: "verb" },
  "saki": { en: "say!", grammar: "verb" },
  "jautāt": { en: "to ask", grammar: "verb" },
  "jautāju": { en: "I ask", grammar: "verb" },
  "jautā": { en: "ask!", grammar: "verb" },
  "atbildēt": { en: "to answer", grammar: "verb" },
  "atbildu": { en: "I answer", grammar: "verb" },
  "atbild": { en: "answer!", grammar: "verb" },
  "palīdzēt": { en: "to help", grammar: "verb" },
  "palīdzu": { en: "I help", grammar: "verb" },
  "palīdz": { en: "help!", grammar: "verb" },
  "gaidīt": { en: "to wait", grammar: "verb" },
  "gaidu": { en: "I wait", grammar: "verb" },
  "gaidi": { en: "wait!", grammar: "verb" },
  "iet": { en: "to go", grammar: "verb" },
  "eju": { en: "I go", grammar: "verb" },
  "ej": { en: "go!", grammar: "verb" },
  "nākt": { en: "to come", grammar: "verb" },
  "nāku": { en: "I come", grammar: "verb" },
  "nāk": { en: "come!", grammar: "verb" },
  "braukt": { en: "to drive, to travel", grammar: "verb" },
  "braucu": { en: "I drive/travel", grammar: "verb" },
  "brauc": { en: "drive!", grammar: "verb" },
  "brauciens": { en: "trip, journey", grammar: "noun" },
  "staigāt": { en: "to walk", grammar: "verb" },
  "staigāju": { en: "I walk", grammar: "verb" },
  "lidot": { en: "to fly", grammar: "verb" },
  "lidmošu": { en: "I fly", grammar: "verb" },
  "peldēt": { en: "to swim", grammar: "verb" },
  "peldu": { en: "I swim", grammar: "verb" },
  "skujust": { en: "to rush, hurry", grammar: "verb" },
  "skubinu": { en: "I rush", grammar: "verb" },
  "kontrolēt": { en: "to check", grammar: "verb" },
  "kontrolē": { en: "check!", grammar: "verb" },
  "nopirkt": { en: "to buy", grammar: "verb" },
  "pērku": { en: "I buy", grammar: "verb" },
  "pirkt": { en: "buy!", grammar: "verb" },
  "pārdot": { en: "to sell", grammar: "verb" },
  "pārdodu": { en: "I sell", grammar: "verb" },
  "maksāt": { en: "to pay", grammar: "verb" },
  "maksāju": { en: "I pay", grammar: "verb" },
  "maksā": { en: "pay!", grammar: "verb" },
  "iet uz": { en: "go to", grammar: "verb phrase" },
  "atgriezties": { en: "to return", grammar: "verb" },
  "atgriežos": { en: "I return", grammar: "verb" },
  "palikt": { en: "to stay, remain", grammar: "verb" },
  "palieku": { en: "I stay", grammar: "verb" },
  "doties": { en: "to go (somewhere)", grammar: "verb" },
  "dodos": { en: "I go", grammar: "verb" },
  "celies": { en: "get up!", grammar: "verb" },
  "gulties": { en: "to lie down", grammar: "verb" },
  "gulēt": { en: "to sleep", grammar: "verb" },
  "gulēju": { en: "I sleep", grammar: "verb" },
  "gul": { en: "sleep!", grammar: "verb" },
  "mosties": { en: "to wake up", grammar: "verb" },
  "mostos": { en: "I wake up", grammar: "verb" },
  "celt": { en: "to get up, lift", grammar: "verb" },
  "celties": { en: "to get up", grammar: "verb" },
  "sēdēt": { en: "to sit", grammar: "verb" },
  "sēžu": { en: "I sit", grammar: "verb" },
  "sēdi": { en: "sit!", grammar: "verb" },
  "stāvēt": { en: "to stand", grammar: "verb" },
  "stāvu": { en: "I stand", grammar: "verb" },
  "stāv": { en: "stand!", grammar: "verb" },
  "gait": { en: "walk, step", grammar: "noun" },
  "kāja": { en: "leg, foot", grammar: "noun" },
  "roka": { en: "arm, hand", grammar: "noun" },
  "acs": { en: "eye", grammar: "noun" },
  "acs": { en: "eye", grammar: "noun" },
  "mute": { en: "mouth", grammar: "noun" },
  "deguns": { en: "nose", grammar: "noun" },
  "auss": { en: "ear", grammar: "noun" },
  "zobi": { en: "teeth", grammar: "noun" },
  "mati": { en: "hair", grammar: "noun" },
  "seja": { en: "face", grammar: "noun" },
  "galva": { en: "head", grammar: "noun" },
  "kakls": { en: "neck", grammar: "noun" },
  "plecs": { en: "shoulder", grammar: "noun" },
  "vēders": { en: "stomach", grammar: "noun" },
  "mugura": { en: "back", grammar: "noun" },
  "kāja": { en: "leg, foot", grammar: "noun" },
  "vieta": { en: "place", grammar: "noun" },
  "laiks": { en: "time", grammar: "noun" },
  "diena": { en: "day", grammar: "noun" },
  "nakts": { en: "night", grammar: "noun" },
  "rīts": { en: "morning", grammar: "noun" },
  "vakars": { en: "evening", grammar: "noun" },
  "pēcpusdiena": { en: "afternoon", grammar: "noun" },
  "priekšdiena": { en: "yesterday", grammar: "noun" },
  "šodiena": { en: "today", grammar: "noun" },
  "rītdiena": { en: "tomorrow", grammar: "noun" },
  "nedēļa": { en: "week", grammar: "noun" },
  "mēnesis": { en: "month", grammar: "noun" },
  "gads": { en: "year", grammar: "noun" },
  "stunda": { en: "hour", grammar: "noun" },
  "minūte": { en: "minute", grammar: "noun" },
  "sekunde": { en: "second", grammar: "noun" },
  "datums": { en: "date", grammar: "noun" },
  "gadu": { en: "year (acc)", grammar: "noun" },
  "reize": { en: "time (occasion)", grammar: "noun" },
  "reizes": { en: "times", grammar: "noun" },
  "nauda": { en: "money", grammar: "noun" },
  "cents": { en: "cent", grammar: "noun" },
  "eiro": { en: "euro", grammar: "noun" },
  "cena": { en: "price", grammar: "noun" },
  "atzīme": { en: "grade, mark", grammar: "noun" },
  "vērtība": { en: "value", grammar: "noun" },
  "skaits": { en: "number, count", grammar: "noun" },
  "daudzums": { en: "quantity", grammar: "noun" },
  "summa": { en: "sum, total", grammar: "noun" },
  "atlikums": { en: "change (money)", grammar: "noun" },
  "čeks": { en: "receipt", grammar: "noun" },
  "rēķins": { en: "bill, invoice", grammar: "noun" },
  "māja": { en: "home, house", grammar: "noun" },
  "dzīvi": { en: "alive, living", grammar: "adv" },
  "dzīvo": { en: "live", grammar: "verb" },
  "ceļš": { en: "road, way", grammar: "noun" },
  "iela": { en: "street", grammar: "noun" },
  "novads": { en: "region, district", grammar: "noun" },
  "valsts": { en: "country, state", grammar: "noun" },
  "karte": { en: "map", grammar: "noun" },
  "adrese": { en: "address", grammar: "noun" },
  "numurs": { en: "number", grammar: "noun" },
  "tālrunis": { en: "phone", grammar: "noun" },
  "epasts": { en: "email", grammar: "noun" },
  "internets": { en: "internet", grammar: "noun" },
  "dators": { en: "computer", grammar: "noun" },
  "planšete": { en: "tablet", grammar: "noun" },
  "viedtālrunis": { en: "smartphone", grammar: "noun" },
  "bibliotēka": { en: "library", grammar: "noun" },
  "muzejs": { en: "museum", grammar: "noun" },
  "teātris": { en: "theater", grammar: "noun" },
  "kino": { en: "cinema", grammar: "noun" },
  "parks": { en: "park", grammar: "noun" },
  "baseins": { en: "pool", grammar: "noun" },
  "pludmale": { en: "beach", grammar: "noun" },
  "mežs": { en: "forest", grammar: "noun" },
  "kalns": { name: "mountain", grammar: "noun" },
  "ezers": { en: "lake", grammar: "noun" },
  "upe": { en: "river", grammar: "noun" },
  "jūra": { en: "sea", grammar: "noun" },
  "ozeāns": { en: "ocean", grammar: "noun" },
  "salds": { en: "sweet", grammar: "adj" },
  "skābs": { en: "sour", grammar: "adj" },
  "sāļš": { en: "salty", grammar: "adj" },
  "rūgts": { en: "bitter", grammar: "adj" },
  "as": { en: "sharp, spicy", grammar: "adj" },
  "garšīgs": { en: "tasty", grammar: "adj" },
  "negaršīgs": { en: "tasteless, bad-tasting", grammar: "adj" },
  "produkts": { en: "product", grammar: "noun" },
  "ēdiens": { en: "food", grammar: "noun" },
  "ēdiens": { en: "food, meal", grammar: "noun" },
  "brokastis": { en: "breakfast", grammar: "noun" },
  "pusdienas": { en: "lunch", grammar: "noun" },
  "vakariņas": { en: "dinner, supper", grammar: "noun" },
  "maize": { en: "bread", grammar: "noun" },
  "siers": { en: "cheese", grammar: "noun" },
  "putns": { en: "bird", grammar: "noun" },
  "gaļa": { en: "meat", grammar: "noun" },
  "zivs": { en: "fish", grammar: "noun" },
  "dārzenis": { en: "vegetable", grammar: "noun" },
  "auglis": { en: "fruit", grammar: "noun" },
  "ābols": { en: "apple", grammar: "noun" },
  "banāns": { en: "banana", grammar: "noun" },
  "apelsīns": { en: "orange (fruit)", grammar: "noun" },
  "kafija": { en: "coffee", grammar: "noun" },
  "tēja": { en: "tea", grammar: "noun" },
  "sula": { en: "juice", grammar: "noun" },
  "ūdens": { en: "water", grammar: "noun" },
  "pieniens": { en: "milk", grammar: "noun" },
  "alie": { en: "oil", grammar: "noun" },
  "sāls": { en: "salt", grammar: "noun" },
  "cukurs": { en: "sugar", grammar: "noun" },
  "milti": { en: "flour", grammar: "noun" },
  "olas": { en: "eggs", grammar: "noun" },
  "kūka": { en: "cake", grammar: "noun" },
  "cepums": { en: "cookie, biscuit", grammar: "noun" },
  "konfekte": { en: "candy", grammar: "noun" },
  "šokolāde": { en: "chocolate", grammar: "noun" },
  "logs": { en: "window", grammar: "noun" },
  "dvēsele": { en: "soul", grammar: "noun" },
  "prāts": { en: "mind, intellect", grammar: "noun" },
  "doma": { en: "thought", grammar: "noun" },
  "jēga": { en: "meaning, sense", grammar: "noun" },
  "viedoklis": { en: "opinion", grammar: "noun" },
  "atzinība": { en: "recognition", grammar: "noun" },
  "paldies": { en: "thank you", grammar: "phrase" },
  "lūdzu": { en: "please / you're welcome", grammar: "phrase" },
  "atvainojiet": { en: "excuse me, sorry", grammar: "phrase" },
  "žēl": { en: "pity, sorry", grammar: "phrase" },
  "dievs": { en: "God", grammar: "noun" },
  "svētki": { en: "holiday, celebration", grammar: "noun" },
  "Ziemassvētki": { en: "Christmas", grammar: "noun" },
  "Jaunais gads": { en: "New Year", grammar: "noun" },
  "Lieldienas": { en: "Easter", grammar: "noun" },
  "dzimšanas diena": { en: "birthday", grammar: "noun" },
  "vecums": { en: "age", grammar: "noun" },
  "augums": { en: "height, stature", grammar: "noun" },
  "svars": { en: "weight", grammar: "noun" },
  "izmērs": { en: "size", grammar: "noun" },
  "krāsa": { en: "color", grammar: "noun" },
  "forma": { en: "form, shape", grammar: "noun" },
  "tips": { en: "type", grammar: "noun" },
  "veids": { en: "kind, way", grammar: "noun" },
  "veids": { en: "kind, way", grammar: "noun" },
  "stils": { en: "style", grammar: "noun" },
  "modes": { en: "fashion", grammar: "noun" },
  "apģērbs": { en: "clothing", grammar: "noun" },
  "krekls": { en: "shirt", grammar: "noun" },
  "jaka": { en: "jacket", grammar: "noun" },
  "zābaks": { en: "boot", grammar: "noun" },
  "kurpe": { en: "shoe", grammar: "noun" },
  "cepure": { en: "cap, hat", grammar: "noun" },
  "šalle": { en: "scarf", grammar: "noun" },
  "cimds": { en: "glove", grammar: "noun" },
  "spilvens": { en: "pillow", grammar: "noun" },
  "sediens": { en: "blanket", grammar: "noun" },
  "gulta": { en: "bed", grammar: "noun" },
  "galds": { en: "table", grammar: "noun" },
  "krēsls": { en: "chair", grammar: "noun" },
  "sols": { en: "bench", grammar: "noun" },
  "naktsgaldiņš": { en: "nightstand", grammar: "noun" },
  "plaukts": { en: "wardrobe", grammar: "noun" },
  "trauks": { en: "dish, vessel", grammar: "noun" },
  "bļoda": { en: "bowl", grammar: "noun" },
  "krūze": { en: "mug, cup", grammar: "noun" },
  "karote": { en: "spoon", grammar: "noun" },
  "nažs": { en: "knife", grammar: "noun" },
  "dakšiņa": { en: "fork", grammar: "noun" },
  "katls": { en: "pot", grammar: "noun" },
  "panna": { en: "pan", grammar: "noun" },
  "trauku mašīna": { en: "dishwasher", grammar: "noun" },
  "veļas mašīna": { en: "washing machine", grammar: "noun" },
  "ledusskapis": { en: "refrigerator", grammar: "noun" },
  "plīts": { en: "stove", grammar: "noun" },
  "cepinātājs": { en: "toaster", grammar: "noun" },
  "kafijas aparāts": { en: "coffee machine", grammar: "noun" },
  "tālrādis": { en: "TV, television", grammar: "noun" },
  "radio": { en: "radio", grammar: "noun" },
  "telefons": { en: "telephone", grammar: "noun" },
  "dators": { en: "computer", grammar: "noun" },
  "klēvdators": { en: "laptop", grammar: "noun" },
  "planšete": { en: "tablet", grammar: "noun" },
  "printeris": { en: "printer", grammar: "noun" },
  "fakss": { en: "fax machine", grammar: "noun" },
  "svars": { en: "scales", grammar: "noun" },
  "termometrs": { en: "thermometer", grammar: "noun" },
  "pulvers": { en: "fire extinguisher", grammar: "noun" },
  "pirmā palīdzība": { en: "first aid", grammar: "noun" },
  "ātrā palīdzība": { en: "ambulance", grammar: "noun" },
  "ugunsdzēsējs": { en: "firefighter", grammar: "noun" },
  "policija": { en: "police", grammar: "noun" },
  "tiesa": { en: "court", grammar: "noun" },
  "cietums": { en: "prison", grammar: "noun" },
  "nakts": { en: "night", grammar: "noun" },
  "diena": { en: "day", grammar: "noun" },
  "rīts": { en: "morning", grammar: "noun" },
  "pēcpusdiena": { en: "afternoon", grammar: "noun" },
  "vakars": { en: "evening", grammar: "noun" },
  "nakam": { en: "next", grammar: "adv" },
  "pagājušais": { en: "last, previous", grammar: "adj" },
  "šis": { en: "this", grammar: "pron" },
  "tas": { en: "that", grammar: "pron" },
  "viņš": { en: "he", grammar: "pron" },
  "viņa": { en: "she", grammar: "pron" },
  "viņi": { en: "they (masc)", grammar: "pron" },
  "viņas": { en: "they (fem)", grammar: "pron" },
  "es": { en: "I", grammar: "pron" },
  "tu": { en: "you (sing)", grammar: "pron" },
  "mēs": { en: "we", grammar: "pron" },
  "jūs": { en: "you (pl)", grammar: "pron" },
  "kas": { en: "what, who", grammar: "pron" },
  "kas": { en: "what, who", grammar: "pron" },
  "kurš": { en: "which (masc)", grammar: "pron" },
  "kura": { en: "which (fem)", grammar: "pron" },
  "kurš": { en: "which", grammar: "pron" },
  "kur": { en: "where", grammar: "adv" },
  "kad": { en: "when", grammar: "adv" },
  "kā": { en: "how", grammar: "adv" },
  "kāpēc": { en: "why", grammar: "adv" },
  "cik": { en: "how many", grammar: "adv" },
  "cits": { en: "other, another", grammar: "adj" },
  "cita": { en: "other", grammar: "adj" },
  "cits": { en: "other", grammar: "adj" },
  "pašlaik": { en: "now, currently", grammar: "adv" },
  "tagad": { en: "now", grammar: "adv" },
  "tad": { en: "then", grammar: "adv" },
  "vēl": { en: "still, yet", grammar: "adv" },
  "jau": { en: "already", grammar: "adv" },
  "tikai": { en: "only", grammar: "adv" },
  "ļoti": { en: "very", grammar: "adv" },
  "pārāk": { en: "too (excessively)", grammar: "adv" },
  "nedaudz": { en: "a little", grammar: "adv" },
  "daudz": { en: "a lot", grammar: "adv" },
  "maz": { en: "little, few", grammar: "adv" },
  "pilnīgi": { en: "completely", grammar: "adv" },
  "galīgi": { en: "absolutely", grammar: "adv" },
  "aptuveni": { en: "approximately", grammar: "adv" },
  "precīzi": { en: "exactly", grammar: "adv" },
  "droši": { en: "surely, safely", grammar: "adv" },
  "noteikti": { en: "certainly", grammar: "adv" },
  "varbūt": { en: "maybe", grammar: "adv" },
  "protams": { en: "of course", grammar: "adv" },
  "diemžēl": { en: "unfortunately", grammar: "adv" },
  "laimīgi": { en: "fortunately", grammar: "adv" },
  "patiešām": { en: "really, indeed", grammar: "adv" },
  "vistic": { en: "really", grammar: "adv" },
  "vienkārši": { en: "simply", grammar: "adv" },
  "īstenībā": { en: "in fact", grammar: "adv" },
  "patiesībā": { en: "in truth", grammar: "adv" },
  "nopietni": { en: "seriously", grammar: "adv" },
  "jokā": { en: "jokingly", grammar: "adv" },
  "nopietni": { en: "seriously", grammar: "adv" },
  "tā": { en: "so, thus", grammar: "adv" },
  "citādi": { en: "otherwise", grammar: "adv" },
  "šādā veidā": { en: "in this way", grammar: "phrase" },
  "kaut kā": { en: "somehow", grammar: "phrase" },
  "ko tad": { en: "what then", grammar: "phrase" },
  "gan jau": { en: "I suppose", grammar: "phrase" },
  "nu jau": { en: "now then", grammar: "phrase" },
  "nez kāpēc": { en: "for some reason", grammar: "phrase" },
  "kas zina": { en: "who knows", grammar: "phrase" },
  "Dievs viņš zina": { en: "God knows", grammar: "phrase" },
  "necik": { en: "not much", grammar: "phrase" },
  "vairāk": { en: "more", grammar: "adv" },
  "mazāk": { en: "less", grammar: "adv" },
  "lielākais": { en: "biggest", grammar: "adj" },
  "mazākais": { en: "smallest", grammar: "adj" },
  "labākais": { en: "best", grammar: "adj" },
  "sliktākais": { en: "worst", grammar: "adj" },
  "augstākais": { en: "highest", grammar: "adj" },
  "zemākais": { en: "lowest", grammar: "adj" },
  "vairāk": { en: "more", grammar: "adv" },
  "mazāk": { en: "less", grammar: "adv" },
  "ļoti": { en: "very", grammar: "adv" },
  "pavisam": { en: "completely", grammar: "adv" },
  "pilnīgi": { en: "fully", grammar: "adv" },
  "daļēji": { en: "partially", grammar: "adv" },
  "daļējs": { en: "partial", grammar: "adj" },
  "visa": { en: "all (fem)", grammar: "pron" },
  "visi": { en: "all (masc)", grammar: "pron" },
  " viss": { en: "all", grammar: "pron" },
  "katrs": { en: "each (masc)", grammar: "pron" },
  "katra": { en: "each (fem)", grammar: "pron" },
  "katrs": { en: "every", grammar: "pron" },
  "neviens": { en: "no one", grammar: "pron" },
  "nekas": { en: "nothing", grammar: "pron" },
  "nekur": { en: "nowhere", grammar: "adv" },
  "nekad": { en: "never", grammar: "adv" },
  "ne": { en: "not", grammar: "adv" },
  "nē": { en: "no", grammar: "adv" },
  "arī": { en: "also", grammar: "adv" },
  "vēl": { en: "still, else", grammar: "adv" },
  "jau": { en: "already", grammar: "adv" },
  "tikai": { en: "only, just", grammar: "adv" },
  "tomēr": { en: "however, still", grammar: "adv" },
  "bet": { en: "but", grammar: "conj" },
  "un": { en: "and", grammar: "conj" },
  "vai": { en: "or", grammar: "conj" },
  "jo": { en: "because", grammar: "conj" },
  "lai": { en: "so that, let", grammar: "conj" },
  "ja": { en: "if, when", grammar: "conj" },
  "kaut": { en: "although", grammar: "conj" },
  "kamēr": { en: "while", grammar: "conj" },
  "līdz": { en: "until", grammar: "conj" },
  "tāpēc": { en: "therefore", grammar: "phrase" },
  "tādēļ": { en: "therefore", grammar: "phrase" },
  "tālabad": { en: "that's why", grammar: "phrase" },
  "savo": { en: "own", grammar: "pron" },
  "sava": { en: "own", grammar: "pron" },
  "savs": { en: "own", grammar: "pron" },
  "pats": { en: "self", grammar: "pron" },
  "paties": { en: "oneself", grammar: "pron" }
};
>>>>>>> origin/main

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
=======
(function () {
  // ---------------------------------------------------------------------------
  // ThemeManager — apply theme before any paint
  // ---------------------------------------------------------------------------
  var ThemeManager = {
    apply: function (theme) {
      document.documentElement.setAttribute('data-theme', theme);
      var btn = document.getElementById('theme-toggle');
      if (btn) {
        var result = toggleTheme(theme);
        btn.setAttribute('aria-label', result.ariaLabel);
      }
    },
    toggle: function () {
      var current = document.documentElement.getAttribute('data-theme') || 'light';
      var result = toggleTheme(current);
      ThemeManager.apply(result.theme);
      try { localStorage.setItem('theme', result.theme); } catch (e) {}
    },
    init: function () {
      var stored;
      try { stored = localStorage.getItem('theme'); } catch (e) {}
      if (stored === 'dark' || stored === 'light') {
        ThemeManager.apply(stored);
>>>>>>> origin/main
      }
    }
  };

  // Apply theme synchronously before any DOM manipulation / paint
  ThemeManager.init();

  // ---------------------------------------------------------------------------
  // State — in-memory application state
  // ---------------------------------------------------------------------------
  var State = {
    catalog: [],
    filtered: [],
    selectedIndex: -1,
    isPlaying: false,
    currentTime: 0,
    duration: 0,
    waveformData: null
  };
  var isDev = window.location.hostname === 'localhost' || window.location.hostname.indexOf('127.0.0.1') !== -1;
  var audioSource = new AudioSource(AudioSourceType.MP3, window.AUDIO_BASE_URL || '');
  var analyticsTracker = createAnalyticsTracker(isDev ? null : window.ANALYTICS_SINK_URL || null);

  // ---------------------------------------------------------------------------
  // SkeletonHelper — show/hide skeleton loading states
  // ---------------------------------------------------------------------------
  var SkeletonHelper = {
    showSidebar: function() {
      document.querySelectorAll('#menu .skeleton-item').forEach(function(el) { el.hidden = false; });
      document.querySelectorAll('#menu .audio-item').forEach(function(el) { el.hidden = true; });
    },
    hideSidebar: function() {
      document.querySelectorAll('#menu .skeleton-item').forEach(function(el) { el.hidden = true; });
    },
    showPanels: function() {
      document.querySelectorAll('.panel-body .skeleton-line').forEach(function(el) { el.hidden = false; });
      document.querySelectorAll('.reading-text').forEach(function(el) { el.hidden = true; });
    },
    hidePanels: function() {
      document.querySelectorAll('.panel-body .skeleton-line').forEach(function(el) { el.hidden = true; });
      document.querySelectorAll('.reading-text').forEach(function(el) { el.hidden = false; });
    }
  };

  // ---------------------------------------------------------------------------
  // ProgressTracker — localStorage-backed lesson completion tracking
  // ---------------------------------------------------------------------------
  var ProgressTracker = {
    _completed: {},
    load: function() {
      try {
        var raw = localStorage.getItem('lll_completed');
        if (raw) ProgressTracker._completed = JSON.parse(raw);
      } catch(e) {}
    },
    save: function(id) {
      ProgressTracker._completed[id] = true;
      try {
        localStorage.setItem('lll_completed', JSON.stringify(ProgressTracker._completed));
      } catch(e) {}
      ProgressTracker.updateUI();
    },
    isCompleted: function(id) {
      return ProgressTracker._completed[id] === true;
    },
    getCompleted: function() {
      return ProgressTracker._completed;
    },
    updateUI: function() {
      // Update completion dots on sidebar buttons
      var buttons = document.querySelectorAll('.audio-item[data-lesson-id]');
      buttons.forEach(function(btn) {
        var id = btn.getAttribute('data-lesson-id');
        var dot = btn.querySelector('.completion-dot');
        if (dot) {
          if (ProgressTracker.isCompleted(id)) {
            btn.classList.add('completed');
          } else {
            btn.classList.remove('completed');
          }
        }
      });
      // Update progress bar for current level
      var item = State.filtered[State.selectedIndex];
      if (!item) return;
      var levelItems = State.catalog.filter(function(l) { return l.level === item.level; });
      var levelIds = levelItems.map(function(l) { return l.id; });
      var progress = calcProgress(levelIds, ProgressTracker._completed);
      var bar = document.getElementById('level-progress-bar');
      var label = document.getElementById('level-progress-label');
      if (bar) {
        bar.setAttribute('aria-valuenow', progress.valuenow);
        bar.style.width = progress.valuenow + '%';
      }
      if (label) label.textContent = progress.label;
      // Show/hide exam readiness
      var examItems = levelItems.filter(function(l) { return l.exam; });
      var examEl = document.getElementById('exam-readiness');
      var examPct = document.getElementById('exam-pct');
      if (examEl && examItems.length > 0) {
        var examCompleted = examItems.filter(function(l) { return ProgressTracker.isCompleted(l.id); }).length;
        var pct = Math.round(examCompleted / examItems.length * 100);
        if (examPct) examPct.textContent = pct + '%';
        examEl.hidden = false;
      } else if (examEl) {
        examEl.hidden = true;
      }
    }
  };
  ProgressTracker.load();

  // ---------------------------------------------------------------------------
  // DOM references
  // ---------------------------------------------------------------------------
  var menu = document.querySelector('#menu');
  var search = document.querySelector('#search');
  var styleFilter = document.querySelector('#styleFilter');
  var categoryFilter = document.querySelector('#categoryFilter');
  var title = document.querySelector('#title');
  var subtitle = document.querySelector('#subtitle');
  var audio = document.querySelector('#audio');

  // Wire timeupdate to track completion via ProgressTracker
  if (audio) {
    audio.addEventListener('timeupdate', function() {
      var item = State.filtered[State.selectedIndex];
      if (item && isCompleted(audio.currentTime, audio.duration)) {
        ProgressTracker.save(item.id);
      }
    });
  }

function selectItem(index) {
  if (index < 0 || index >= State.filtered.length) return;
  State.selectedIndex = index;
  var item = State.filtered[index];
  if (title) setText(title, item.title || item.original_filename, "Untitled audio");
  if (subtitle) setText(subtitle, (levelLabels[item.level] || item.level) + ' · ' + (item.original_filename || ""), "");
  if (audio) audio.src = item.audio_url || "";
  if (lvText) setText(lvText, item.lv_text, "Latvian transcript is not available yet.");
  if (enText) setText(enText, item.en_text, "English translation is not available yet.");
  if (lvLink) lvLink.href = item.lv_markdown_url || "#";
  if (enLink) enLink.href = item.en_markdown_url || "#";
  if (statusBadge) { statusBadge.textContent = item.status || "unknown"; statusBadge.className = badgeClass(item.status); }
  if (previousButton) previousButton.disabled = State.selectedIndex <= 0;
  if (nextButton) nextButton.disabled = State.selectedIndex >= State.filtered.length - 1;
  renderMenu();
  var activeTab = document.querySelector('.tab.active');
  if (activeTab && activeTab.id === 'vocabTabBtn') {
    showVocabTab();
  }
}

var lvText = document.querySelector('#lvText');
var enText = document.querySelector('#enText');
var lvLink = document.querySelector('#lvLink');
  var enLink = document.querySelector('#enLink');
  var statusBadge = document.querySelector('#statusBadge');
  var speakerBadge = document.querySelector('#speakerBadge');
  var previousButton = document.querySelector('#prev');
  var nextButton = document.querySelector('#next');
  var voiceRecommendation = document.querySelector('#voiceRecommendation');
  var compBarFill = document.querySelector('#compBarFill');
  var compPct = document.querySelector('#compPct');
  var compLabel = document.querySelector('#compLabel');
  var compEstimateNote = document.querySelector('#compEstimateNote');
  var compMeterCard = document.querySelector('#compMeterCard');
  var statTotal = document.querySelector('#statTotal');
  var statUnique = document.querySelector('#statUnique');
  var statUnknown = document.querySelector('#statUnknown');
  var unknownWordList = document.querySelector('#unknownWordList');
  var activeCompFilter = 'all';
  var aiService = window.AIExplanationService ? new window.AIExplanationService() : null;
  var currentExplanationSentence = null;
  var aiPanel = document.querySelector('#aiPanel');
  var aiPanelContent = document.querySelector('#aiPanelContent');
  var aiLoading = document.querySelector('#aiLoading');
  var aiError = document.querySelector('#aiError');
  var aiOverlay = document.querySelector('#aiOverlay');
  var closeAIPanelBtn = document.querySelector('#closeAIPanel');
  var aiModeToggle = document.querySelector('#aiModeToggle');
  var retryBtn = document.querySelector('#retryBtn');
var vocabMenu = document.querySelector("#vocabMenu");
  var vocabSearch = document.querySelector("#vocabSearch");
  var vocabTabBtn = document.querySelector("#vocabTabBtn");
  var flashcardModal = document.querySelector("#flashcardModal");
  var flashcardWord = document.querySelector("#flashcardWord");
  var flashcardTranslation = document.querySelector("#flashcardTranslation");
  var flashcardExample = document.querySelector("#flashcardExample");
  var flashcardGrammar = document.querySelector("#flashcardGrammar");
  var flashcardFront = document.querySelector("#flashcardFront");
  var flashcardBack = document.querySelector("#flashcardBack");

  if (audio) {
    audio.addEventListener('play', function() {
      var item = State.filtered[State.selectedIndex];
      if (item) {
        analyticsTracker.track(Analytics.EventTypes.AUDIO_PLAY, {
          lesson_id: item.id,
          filename: item.original_filename
        });
      }
    });
    audio.addEventListener('pause', function() {
      var item = State.filtered[State.selectedIndex];
      if (item && !audio.ended) {
        analyticsTracker.track(Analytics.EventTypes.AUDIO_PAUSE, {
          lesson_id: item.id,
          filename: item.original_filename
        });
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------
  var levelLabels = {
    A1: 'A1 Klausīšanās',
    A2: 'A2 Klausīšanās',
  };

function extractVocabulary(transcript) {
  if (!transcript) return [];
  var words = transcript.toLowerCase().replace(/[.,!?;:"''()[\]{}]/g, ' ').split(/\s+/).filter(function(w) { return w.length > 2 && !STOPWORDS.has(w); });
  var wordCounts = {};
  words.forEach(function(w) { wordCounts[w] = (wordCounts[w] || 0) + 1; });
  return Object.entries(wordCounts).sort(function(a, b) { return b[1] - a[1]; }).slice(0, 20).map(function(_ref) {
    var word = _ref[0];
    var dictEntry = VOCAB_DICTIONARY[word];
    return { word: word, en: dictEntry ? dictEntry.en : '—', grammar: dictEntry ? dictEntry.grammar : 'noun', lemma: word };
  });
}

function loadDeck() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; }
  catch { return []; }
}

function saveDeck(deck) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(deck));
}

function getDueCards() {
  var deck = loadDeck();
  var now = Date.now();
  return deck.filter(function(card) { return card.due <= now; });
}

function getMissedCards() {
  var deck = loadDeck();
  return deck.filter(function(card) { return card.incorrect > card.correct; }).sort(function(a, b) { return (b.incorrect - b.correct) - (a.incorrect - a.correct); });
}

function addCard(word, en, example, lemma, grammar) {
  var deck = loadDeck();
  if (deck.some(function(c) { return c.word === word; })) return false;
  deck.push({ word: word, en: en, example: example, lemma: lemma, grammar: grammar, ease: 2.5, interval: 0, due: Date.now(), correct: 0, incorrect: 0 });
  saveDeck(deck);
  return true;
}

function reviewCard(word, rating) {
  var deck = loadDeck();
  var card = deck.find(function(c) { return c.word === word; });
  if (!card) return;
  if (rating === 'again') { card.incorrect++; card.interval = 0; card.due = Date.now() + 60000; }
  else if (rating === 'good') { card.correct++; card.interval = Math.max(1, card.interval * card.ease); card.due = Date.now() + card.interval * 24 * 60 * 60 * 1000; }
  else if (rating === 'easy') { card.correct++; card.ease = Math.min(3.0, card.ease + 0.15); card.interval = Math.max(1, card.interval * card.ease * 1.3); card.due = Date.now() + card.interval * 24 * 60 * 60 * 1000; }
  saveDeck(deck);
}

function exportAnkiCSV() {
  const deck = loadDeck();
  const lessonTitle = filtered[selectedIndex]?.title || 'Unknown';
  let csv = 'Latvian,English,Example,Lemma\n';
  deck.forEach(card => { csv += `"${card.word}","${card.en}","${(card.example || '').replace(/"/g, '""')}","${card.lemma || ''}"\n`; });
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `latvian_flashcards_${lessonTitle.replace(/\s+/g, '_')}.csv`; link.click();
}

function exportDeckJSON() {
  const deck = loadDeck();
  const blob = new Blob([JSON.stringify(deck, null, 2)], { type: 'application/json' });
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'latvian_flashcards_backup.json'; link.click();
}

function importDeckJSON(file) {
  const reader = new FileReader();
  reader.onload = (e) => { try { const deck = JSON.parse(e.target.result); if (Array.isArray(deck)) { saveDeck(deck); alert('Deck imported!'); } } catch { alert('Invalid file'); } };
  reader.readAsText(file);
}

const vocabSection = document.getElementById('vocabSection');
const reviewSection = document.getElementById('reviewSection');
const deckSection = document.getElementById('deckSection');

function showVocabTab() {
  if (vocabSection) vocabSection.style.display = 'block';
  if (reviewSection) reviewSection.style.display = 'none';
  if (deckSection) deckSection.style.display = 'none';
  const vocabList = document.getElementById('vocabList');
  if (!vocabList) return;
  const item = filtered[selectedIndex];
  const vocab = extractVocabulary(item?.lv_text || '');
  vocabList.innerHTML = '';
  vocab.forEach(v => {
    const row = document.createElement('div');
    row.className = 'vocab-row';
    const wordEl = document.createElement('span');
    wordEl.className = 'vocab-word';
    wordEl.textContent = v.word;
    const enEl = document.createElement('span');
    enEl.className = 'vocab-en';
    enEl.textContent = v.en;
    const grammarEl = document.createElement('small');
    grammarEl.className = 'vocab-grammar';
    grammarEl.textContent = v.grammar;
    const saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'btn-save';
    saveBtn.textContent = '+ Flashcard';
    const existing = loadDeck();
    const alreadySaved = existing.some(c => c.word === v.word);
    if (alreadySaved) { saveBtn.textContent = 'Saved'; saveBtn.disabled = true; }
    else { saveBtn.onclick = () => { const ex = item?.lv_text?.split('\n').find(l => l.includes(v.word)) || ''; if (addCard(v.word, v.en, ex, v.lemma, v.grammar)) { saveBtn.textContent = 'Saved'; saveBtn.disabled = true; } }; }
    row.append(wordEl, enEl, grammarEl, saveBtn);
    vocabList.appendChild(row);
  });
  if (!vocab.length) { vocabList.innerHTML = '<p class="empty">No vocabulary found in transcript.</p>'; }
}

function showReviewTab() {
  if (vocabSection) vocabSection.style.display = 'none';
  if (reviewSection) reviewSection.style.display = 'block';
  if (deckSection) deckSection.style.display = 'none';
  const reviewContainer = document.getElementById('reviewContainer');
  if (!reviewContainer) return;
  const due = getDueCards();
  if (!due.length) { reviewContainer.innerHTML = '<p class="empty">No cards due for review.</p>'; return; }
  const card = due[0];
  reviewContainer.innerHTML = '';
  const cardEl = document.createElement('div');
  cardEl.className = 'flashcard';
  const front = document.createElement('div');
  front.className = 'flashcard-front';
  front.textContent = card.word;
  const back = document.createElement('div');
  back.className = 'flashcard-back';
  back.textContent = `${card.en} (${card.grammar})`;
  back.style.display = 'none';
  const revealBtn = document.createElement('button');
  revealBtn.type = 'button';
  revealBtn.className = 'btn-reveal';
  revealBtn.textContent = 'Reveal';
  revealBtn.onclick = () => { back.style.display = 'block'; revealBtn.style.display = 'none'; showAnswerButtons(card.word); };
  cardEl.append(front, back, revealBtn);
  reviewContainer.appendChild(cardEl);
}

function showAnswerButtons(word) {
  const reviewContainer = document.getElementById('reviewContainer');
  const btns = document.createElement('div');
  btns.className = 'review-buttons';
  [['again', 'Again'], ['good', 'Good'], ['easy', 'Easy']].forEach(([rating, label]) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `btn-${rating}`;
    btn.textContent = label;
    btn.onclick = () => { reviewCard(word, rating); showReviewTab(); };
    btns.appendChild(btn);
  });
  reviewContainer.appendChild(btns);
}

function showDeckTab() {
  if (vocabSection) vocabSection.style.display = 'none';
  if (reviewSection) reviewSection.style.display = 'none';
  if (deckSection) deckSection.style.display = 'block';
  const deckStats = document.getElementById('deckStats');
  if (!deckStats) return;
  const deck = loadDeck();
  const due = getDueCards().length;
  const missed = getMissedCards();
  deckStats.innerHTML = `<p>Total cards: ${deck.length}</p><p>Due now: ${due}</p><p>Needs work: ${missed.length}</p>`;
  const deckList = document.getElementById('deckList');
  if (!deckList) return;
  deckList.innerHTML = '';
  deck.slice(0, 20).forEach(card => {
    const row = document.createElement('div');
    row.className = 'deck-row';
    row.innerHTML = `<span>${card.word}</span><span>${card.correct}/${card.incorrect}</span><span>${card.interval ? Math.round(card.interval) + 'd' : 'new'}</span>`;
    deckList.appendChild(row);
  });
}

const vocabBtn = document.getElementById('vocabTabBtn');
const reviewBtn = document.getElementById('reviewTabBtn');
const deckBtn = document.getElementById('deckTabBtn');
if (vocabBtn) vocabBtn.addEventListener('click', showVocabTab);
if (reviewBtn) reviewBtn.addEventListener('click', showReviewTab);
if (deckBtn) deckBtn.addEventListener('click', showDeckTab);
if (vocabBtn) showVocabTab();

const exportAnkiBtn = document.getElementById('exportAnkiBtn');
const exportJsonBtn = document.getElementById('exportJsonBtn');
const importJsonBtn = document.getElementById('importJsonBtn');
if (exportAnkiBtn) exportAnkiBtn.addEventListener('click', exportAnkiCSV);
if (exportJsonBtn) exportJsonBtn.addEventListener('click', exportDeckJSON);
if (importJsonBtn) importJsonBtn.addEventListener('change', (e) => { if (e.target.files[0]) importDeckJSON(e.target.files[0]); });

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
=======
  var voiceTypeLabels = {
    cashier: 'Cashier',
    doctor: 'Doctor',
    teacher: 'Teacher',
    colleague: 'Colleague',
    driver: 'Bus Driver',
    grandmother: 'Grandmother',
    grandfather: 'Grandfather',
    government: 'Government Office',
    friend: 'Friend',
    landlord: 'Landlord'
  };

  var MODE_KEY = 'latvian_listening_library_mode';
  var SCENARIO_PROGRESS_KEY = 'latvian_listening_library_progress';
  var currentMode = localStorage.getItem(MODE_KEY) || 'library';
  var scenarioProgress = {};

  try {
    scenarioProgress = JSON.parse(localStorage.getItem(SCENARIO_PROGRESS_KEY)) || {};
  } catch (e) {
    scenarioProgress = {};
  }

  var categoryFilters = {
    family: 'Gimene',
    work: 'Darbs',
    health: 'Veseliba',
    bureaucracy: 'Birokratija',
    transport: 'Transports',
    shopping: 'Iepirksanas'
  };

  var scenarios = [
    {
      id: 'school-call',
      title: 'Zvana uz skolu',
      description: "Communicating with teachers about your child's progress, attendance, or schedule.",
      category: 'family',
      vocabulary: ['skolotajs', 'stunda', 'majasdarbs', 'atzime', 'sapulce', 'kavejums'],
      phrases: [
        { lv: 'Labdien, es gribetu runat ar savas meitas skolotaju.', en: "Hello, I'd like to speak with my daughter's teacher.", context: 'Calling a teacher' },
        { lv: 'Kad ir vecaku sapulce?', en: 'When is the parent meeting?', context: 'Asking about school events' }
      ]
    },
    {
      id: 'doctor',
      title: 'Pie arsta',
      description: 'Making appointments, describing symptoms, and understanding medical instructions.',
      category: 'health',
      vocabulary: ['arsts', 'slimiba', 'simptomi', 'recepte', 'analizes', 'aptieka'],
      phrases: [
        { lv: 'Man sap galva un ir temperatura.', en: 'I have a headache and a fever.', context: 'Describing symptoms' },
        { lv: 'Kad man jaatnak uz kontroli?', en: 'When should I come for a follow-up?', context: 'Follow-up appointment' }
      ]
    },
    {
      id: 'government',
      title: 'Valsts iestade',
      description: 'Visiting municipal offices, population registry, and social services.',
      category: 'bureaucracy',
      vocabulary: ['dokumenti', 'veidlapa', 'rinda', 'apstiprinajums', 'dzivesvieta'],
      phrases: [
        { lv: 'Kur es varu registret dzivesvietu?', en: 'Where can I register my residence?', context: 'Residence registration' },
        { lv: 'Kadi dokumenti man ir nepieciesami?', en: 'What documents do I need?', context: 'Required documents' }
      ]
    },
    {
      id: 'residency',
      title: 'Uzturesanas atlauja',
      description: 'Applying for residence permits, extensions, and understanding requirements.',
      category: 'bureaucracy',
      vocabulary: ['uzturesanas atlauja', 'pieteikums', 'termins', 'maksa', 'intervija'],
      phrases: [
        { lv: 'Es velos pieteikties uzturesanas atlaujai.', en: 'I want to apply for a residence permit.', context: 'Application' },
        { lv: 'Cik ilgi jagaida lemums?', en: 'How long does it take to get a decision?', context: 'Processing time' }
      ]
    },
    {
      id: 'work-meeting',
      title: 'Darba sanaksme',
      description: 'Participating in workplace meetings and understanding tasks.',
      category: 'work',
      vocabulary: ['sanaksme', 'projekts', 'uzdevums', 'termins', 'komanda'],
      phrases: [
        { lv: 'Kads ir projekta grafiks?', en: 'What is the project schedule?', context: 'Project planning' },
        { lv: 'Vai es varu sanemt so informaciju rakstiski?', en: 'Can I get this information in writing?', context: 'Written confirmation' }
      ]
    },
    {
      id: 'transport',
      title: 'Sabiedriskais transports',
      description: 'Buying tickets, asking about routes, schedules, and stops.',
      category: 'transport',
      vocabulary: ['autobuss', 'tramvajs', 'bilete', 'marsruts', 'pietura'],
      phrases: [
        { lv: 'Vai sis autobuss brauc uz centru?', en: 'Does this bus go to the center?', context: 'Route inquiry' },
        { lv: 'Es gribetu izkapt nakamaja pietura.', en: 'I would like to get off at the next stop.', context: 'Requesting a stop' }
      ]
    },
    {
      id: 'grocery',
      title: 'Veikals/Kase',
      description: 'Shopping, asking for products, understanding prices, and payment methods.',
      category: 'shopping',
      vocabulary: ['prece', 'cena', 'atlaide', 'svars', 'kvits'],
      phrases: [
        { lv: 'Kur es varu atrast maizi?', en: 'Where can I find bread?', context: 'Finding products' },
        { lv: 'Vai es varu maksat ar karti?', en: 'Can I pay by card?', context: 'Card payment' }
      ]
>>>>>>> origin/main
    }
  ];

  var askToRepeatPhrases = [
    { lv: 'Ludzu, atkartojiet!', en: 'Please repeat!', context: 'When you need to hear it again' },
    { lv: 'Es nesapratu.', en: "I didn't understand.", context: 'When the meaning is unclear' },
    { lv: 'Vai jus varat runat lenak?', en: 'Can you speak more slowly?', context: 'When speech is too fast' }
  ];

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  function badgeClass(status) {
    if (status === 'completed') return 'badge badge-completed';
    if (status === 'transcribed only' || status === 'translation failed') return 'badge badge-transcribed';
    if (status === 'failed') return 'badge badge-failed';
    return 'badge badge-muted';
  }

  function getSpeakingStyle(item) {
    if (!item) return '';
    return item.speaking_style || item.voice_style || item.style || '';
  }

  function displaySpeakerBadge(item) {
    if (!speakerBadge) return;
    if (!item || !item.has_speaker) {
      speakerBadge.style.display = 'none';
      return;
    }

    var label = item.speaker_label || voiceTypeLabels[item.voice_type] || item.voice_type;
    if (label) {
      speakerBadge.textContent = label;
      speakerBadge.style.display = 'inline-block';
    } else {
      speakerBadge.style.display = 'none';
    }
  }

  function getVoiceRecommendation(currentItem, items) {
    if (!currentItem || !currentItem.has_speaker || !currentItem.voice_type) return '';
    var otherTypes = (items || []).filter(function(item) {
      return item.has_speaker && item.voice_type && item.voice_type !== currentItem.voice_type;
    });
    if (otherTypes.length === 0) return '';

    var nextType = otherTypes[Math.floor(Math.random() * otherTypes.length)].voice_type;
    var label = voiceTypeLabels[nextType] || nextType;
    return 'Try a ' + label + ' voice next.';
  }

  function saveScenarioProgress() {
    localStorage.setItem(SCENARIO_PROGRESS_KEY, JSON.stringify(scenarioProgress));
  }

  function getScenarioProgress(id) {
    return scenarioProgress[id] || 'not_started';
  }

  function setScenarioProgress(id, status) {
    scenarioProgress[id] = status;
    saveScenarioProgress();
  }

  function renderPhraseCards(items) {
    return items.map(function(item) {
      return '<div class="phrase-card">' +
        '<div class="phrase-lv">' + escapeHtml(item.lv) + '</div>' +
        '<div class="phrase-en">' + escapeHtml(item.en) + '</div>' +
        '<div class="phrase-context">' + escapeHtml(item.context || '') + '</div>' +
        '</div>';
    }).join('');
  }

  function renderLivingMenu(filter) {
    if (!menu) return;
    menu.textContent = '';

    var backButton = document.createElement('button');
    backButton.type = 'button';
    backButton.className = 'mode-toggle';
    backButton.textContent = 'Back to library';
    backButton.addEventListener('click', function() {
      currentMode = 'library';
      localStorage.setItem(MODE_KEY, currentMode);
      window.location.reload();
    });
    menu.appendChild(backButton);

    var filterContainer = document.createElement('div');
    filterContainer.className = 'filter-container';
    var select = document.createElement('select');
    select.className = 'form-select';
    select.innerHTML = '<option value="">All real-life topics</option>' +
      Object.keys(categoryFilters).map(function(key) {
        return '<option value="' + key + '">' + categoryFilters[key] + '</option>';
      }).join('');
    select.value = filter || '';
    select.addEventListener('change', function(event) {
      renderLivingMenu(event.target.value);
    });
    filterContainer.appendChild(select);
    menu.appendChild(filterContainer);

    var list = document.createElement('div');
    list.className = 'scenario-list item-list';
    scenarios
      .filter(function(scenario) { return !filter || scenario.category === filter; })
      .forEach(function(scenario) {
        var progress = getScenarioProgress(scenario.id);
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'scenario-item audio-item ' + progress;
        button.innerHTML = '<span class="progress-dot ' + progress + '"></span>' +
          '<span>' + escapeHtml(scenario.title) + '</span>' +
          '<small>' + escapeHtml(categoryFilters[scenario.category] || scenario.category) + '</small>';
        button.addEventListener('click', function() {
          renderScenario(scenario);
        });
        list.appendChild(button);
      });
    menu.appendChild(list);
  }

  function renderLivingHome() {
    var reader = document.querySelector('.reader');
    if (!reader) return;
    var practiced = Object.keys(scenarioProgress).filter(function(key) {
      return scenarioProgress[key] !== 'not_started';
    }).length;
    var confident = Object.keys(scenarioProgress).filter(function(key) {
      return scenarioProgress[key] === 'confident';
    }).length;

    reader.innerHTML =
      '<section class="living-hero hero">' +
        '<div><p class="eyebrow">Praktiskais modulis</p><h2>Dzivo Latvija</h2>' +
        '<p>Practical listening scenarios for everyday life in Latvia.</p></div>' +
        '<span class="badge badge-muted">A2 Level</span>' +
      '</section>' +
      '<section class="living-intro">' +
        '<div class="intro-card"><h3>Scenarios</h3><p>Choose a topic from the sidebar to practice realistic phrases, vocabulary, and clarification requests.</p></div>' +
        '<div class="intro-card"><h3>Your progress</h3><div class="progress-stats">' +
          '<div class="stat"><span class="stat-num">' + practiced + '</span><span class="stat-label">Practiced</span></div>' +
          '<div class="stat"><span class="stat-num">' + confident + '</span><span class="stat-label">Confident</span></div>' +
        '</div></div>' +
      '</section>' +
      '<section class="scenario-grid">' +
        scenarios.map(function(scenario) {
          var progress = getScenarioProgress(scenario.id);
          return '<button type="button" class="scenario-card ' + progress + '" data-scenario-id="' + scenario.id + '">' +
            '<span class="category-tag">' + escapeHtml(categoryFilters[scenario.category] || scenario.category) + '</span>' +
            '<h4>' + escapeHtml(scenario.title) + '</h4>' +
            '<p>' + escapeHtml(scenario.description) + '</p>' +
            '<div class="card-footer"><span class="progress-status">' + progress.replace('_', ' ') + '</span></div>' +
          '</button>';
        }).join('') +
      '</section>';

    reader.querySelectorAll('.scenario-card').forEach(function(card) {
      card.addEventListener('click', function() {
        var scenario = scenarios.find(function(item) { return item.id === card.getAttribute('data-scenario-id'); });
        if (scenario) renderScenario(scenario);
      });
    });
  }

  function renderScenario(scenario) {
    var reader = document.querySelector('.reader');
    if (!reader) return;
    var progress = getScenarioProgress(scenario.id);
    reader.innerHTML =
      '<section class="scenario-hero">' +
        '<div class="scenario-header"><span class="category-badge">' + escapeHtml(categoryFilters[scenario.category] || scenario.category) + '</span>' +
        '<h2>' + escapeHtml(scenario.title) + '</h2><p class="scenario-subtitle">' + escapeHtml(scenario.description) + '</p></div>' +
        '<div class="progress-selector">' +
          '<button class="progress-btn ' + (progress === 'not_started' ? 'active' : '') + '" data-progress="not_started" type="button">Not started</button>' +
          '<button class="progress-btn ' + (progress === 'practiced' ? 'active' : '') + '" data-progress="practiced" type="button">Practiced</button>' +
          '<button class="progress-btn ' + (progress === 'confident' ? 'active' : '') + '" data-progress="confident" type="button">Confident</button>' +
        '</div>' +
      '</section>' +
      '<section class="scenario-section vocabulary-section"><h3>Vocabulary</h3><div class="vocabulary-list">' +
        scenario.vocabulary.map(function(word) { return '<span class="vocab-tag">' + escapeHtml(word) + '</span>'; }).join('') +
      '</div></section>' +
      '<section class="scenario-section phrases-section"><h3>Phrases</h3><div class="phrases-grid">' + renderPhraseCards(scenario.phrases) + '</div></section>' +
      '<section class="scenario-section repeat-section"><h3>Please repeat - mini practice</h3><div class="phrases-grid repeat-phrases">' + renderPhraseCards(askToRepeatPhrases) + '</div></section>' +
      '<section class="scenario-section checklist-section"><h3>Confidence checklist</h3><ul class="checklist">' +
        '<li>I can understand a greeting.</li><li>I can identify time, date, or place.</li><li>I can ask someone to repeat.</li><li>I can answer with a short sentence.</li>' +
      '</ul></section>' +
      '<button class="back-to-scenarios-btn" type="button">Back to scenarios</button>';

    reader.querySelectorAll('.progress-btn').forEach(function(button) {
      button.addEventListener('click', function() {
        setScenarioProgress(scenario.id, button.getAttribute('data-progress'));
        renderLivingMenu();
        renderScenario(scenario);
      });
    });
    var back = reader.querySelector('.back-to-scenarios-btn');
    if (back) back.addEventListener('click', renderLivingHome);
  }

  function enterLivingMode() {
    currentMode = 'living';
    localStorage.setItem(MODE_KEY, currentMode);
    renderLivingMenu();
    renderLivingHome();
  }

  function renderComprehensionMeter(text) {
    if (!compMeterCard || !window.ComprehensionMeter || !text || !text.trim()) {
      if (compMeterCard) compMeterCard.hidden = true;
      return;
    }

    compMeterCard.hidden = false;
    var stats = ComprehensionMeter.computeLessonStats(text);
    var result = ComprehensionMeter.getComprehensionLabel(stats.comprehensionPct);

    if (compBarFill) {
      compBarFill.style.width = stats.comprehensionPct + '%';
      compBarFill.className = 'comp-bar-fill comp-bar-' + result.key;
    }
    if (compPct) compPct.textContent = 'You may understand ~' + stats.comprehensionPct + '%';
    if (compLabel) {
      compLabel.textContent = result.label;
      compLabel.className = 'comp-label comp-label-' + result.key;
    }
    if (compEstimateNote) {
      compEstimateNote.textContent = stats.isEstimate
        ? 'Rough estimate - no vocabulary saved yet'
        : 'Estimate based on your saved words';
    }
    if (statTotal) statTotal.textContent = stats.totalWords;
    if (statUnique) statUnique.textContent = stats.uniqueWords;
    if (statUnknown) statUnknown.textContent = stats.unknownUniqueWords + ' unknown';

    if (!unknownWordList) return;
    unknownWordList.textContent = '';
    if (stats.topUnknownWords.length === 0) {
      var empty = document.createElement('p');
      empty.className = 'unknown-empty';
      empty.textContent = 'Great - no unknown words detected!';
      unknownWordList.appendChild(empty);
      return;
    }

    stats.topUnknownWords.forEach(function(item) {
      var tag = document.createElement('button');
      tag.type = 'button';
      tag.className = 'unknown-word-tag';
      tag.textContent = item.word + (item.count > 1 ? ' (' + item.count + ')' : '');

      var removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'unknown-word-remove';
      removeBtn.textContent = '✓';
      removeBtn.title = 'Mark as known';

      function markKnown() {
        ComprehensionMeter.saveKnownWord(item.word, 'manual');
        renderComprehensionMeter(text);
        applyCombinedFilters();
      }

      tag.addEventListener('click', markKnown);
      removeBtn.addEventListener('click', markKnown);

      var wrap = document.createElement('span');
      wrap.className = 'unknown-word-wrap';
      wrap.append(tag, removeBtn);
      unknownWordList.appendChild(wrap);
    });
  }

  function filterByComprehension(items) {
    if (activeCompFilter === 'all' || !window.ComprehensionMeter) return items;
    return ComprehensionMeter.filterCatalogByLabel(items, activeCompFilter);
  }

  function filterBySpeakingStyle(items) {
    var styleValue = styleFilter ? styleFilter.value : '';
    if (!styleValue) return items;
    return items.filter(function(item) {
      return getSpeakingStyle(item) === styleValue;
    });
  }

  function filterByCategory(items) {
    var categoryValue = categoryFilter ? categoryFilter.value : '';
    if (!categoryValue || !window.CategoryManager) return items;
    return CategoryManager.filterByCategory(items, categoryValue);
  }

  function applyCombinedFilters() {
    var query = search ? search.value.trim() : '';
    State.filtered = filterByCategory(filterBySpeakingStyle(filterByComprehension(applyFilter(State.catalog, query))));
    State.selectedIndex = State.filtered.length ? 0 : -1;
    Renderer.renderMenu(
      State.filtered,
      State.selectedIndex,
      ProgressTracker ? ProgressTracker.getCompleted() : {}
    );
    if (State.filtered.length) {
      Renderer.selectItem(0);
    } else {
      if (compMeterCard) compMeterCard.hidden = true;
      displaySpeakerBadge(null);
      if (voiceRecommendation) voiceRecommendation.textContent = '';
    }
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }

  function parseTranscriptToSentences(text) {
    if (!text) return [];
    return String(text)
      .split(/(?<=[.!?])\s+/)
      .map(function(sentence) { return sentence.trim(); })
      .filter(function(sentence) { return sentence.length > 0; });
  }

  function renderTranscriptWithClickableSentences(text) {
    var sentences = parseTranscriptToSentences(text);
    if (sentences.length === 0) return escapeHtml(text || '');
    return sentences.map(function(sentence, index) {
      return '<span class="sentence-block" data-sentence="' + index + '" title="Click for AI explanation">' +
        escapeHtml(sentence) +
        '</span>';
    }).join(' ');
  }

  function openAIPanel() {
    if (!aiPanel || !aiOverlay) return;
    aiPanel.classList.add('open');
    aiPanel.setAttribute('aria-hidden', 'false');
    aiOverlay.hidden = false;
  }

  function closeAIPanel() {
    if (!aiPanel || !aiOverlay) return;
    aiPanel.classList.remove('open');
    aiPanel.setAttribute('aria-hidden', 'true');
    aiOverlay.hidden = true;
  }

  function setAILoading(isLoading) {
    if (aiLoading) aiLoading.hidden = !isLoading;
    if (aiError) aiError.hidden = true;
    if (isLoading && aiPanelContent) aiPanelContent.textContent = '';
  }

  function displayExplanation(explanation) {
    if (!aiPanelContent) return;
    setAILoading(false);

    var html = '<div class="explanation-section"><h4>Natural Translation</h4><p>' +
      escapeHtml(explanation.naturalTranslation || '') +
      '</p></div>';

    if (explanation.literalTranslation && explanation.literalTranslation !== explanation.naturalTranslation) {
      html += '<div class="explanation-section"><h4>Word-by-Word</h4><p>' +
        escapeHtml(explanation.literalTranslation) +
        '</p></div>';
    }

    if (explanation.vocabulary && explanation.vocabulary.length > 0) {
      html += '<div class="explanation-section"><h4>Key Vocabulary</h4>';
      explanation.vocabulary.forEach(function(item) {
        html += '<div class="vocab-item"><span class="vocab-word">' + escapeHtml(item.word) + '</span>' +
          '<span class="vocab-pos">' + escapeHtml(item.pos || '') + '</span>' +
          '<div class="vocab-meaning">' + escapeHtml(item.meaning || '') + '</div>' +
          (item.example ? '<div class="vocab-example">' + escapeHtml(item.example) + '</div>' : '') +
          '</div>';
      });
      html += '</div>';
    }

    if (explanation.grammarNotes && explanation.grammarNotes.length > 0) {
      html += '<div class="explanation-section"><h4>Grammar Notes</h4>';
      explanation.grammarNotes.forEach(function(note) {
        html += '<div class="grammar-note"><p>' + escapeHtml(note) + '</p></div>';
      });
      html += '</div>';
    }

    aiPanelContent.innerHTML = html;
  }

  function fetchExplanation(sentence) {
    if (!aiService) return;
    currentExplanationSentence = sentence;
    setAILoading(true);

    var item = State.filtered[State.selectedIndex];
    var lessonId = item ? item.id : 'default';
    aiService.setLessonId(lessonId);

    aiService.explainSentence(sentence, { lessonId: lessonId })
      .then(displayExplanation)
      .catch(function(error) {
        console.error('AI explanation error:', error);
        if (aiLoading) aiLoading.hidden = true;
        if (aiError) aiError.hidden = false;
      });
  }

  // ---------------------------------------------------------------------------
  // Renderer — builds and updates DOM for menu, hero, and panels
  // ---------------------------------------------------------------------------
  var Renderer = {
    renderMenu: function(filtered, selectedIndex, completed) {
      completed = completed || {};
      menu.textContent = '';
      if (currentMode === 'living') {
        renderLivingMenu();
        return;
      }
      var levels = ['A1', 'A2'];
      for (var li = 0; li < levels.length; li++) {
        var level = levels[li];
        var items = filtered.filter(function(item) { return item.level === level; });
        var section = document.createElement('section');
        section.className = 'level-section';

        var toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'level-toggle';
        toggle.setAttribute('aria-expanded', 'true');
        toggle.textContent = (levelLabels[level] || level) + ' (' + items.length + ')';
        var plus = document.createElement('span');
        plus.textContent = '−';
        toggle.appendChild(plus);

        var list = document.createElement('div');
        list.className = 'item-list';

        for (var ii = 0; ii < items.length; ii++) {
          (function(item) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'audio-item';
            button.setAttribute('data-lesson-id', item.id || '');

            // Apply active class to the selected item only
            if (filtered[selectedIndex] && filtered[selectedIndex].id === item.id) {
              button.classList.add('active');
            }

            // Apply completed class if lesson is in completed map
            if (completed[item.id] === true) {
              button.classList.add('completed');
            }

            button.addEventListener('click', function() {
              var newIndex = filtered.findIndex(function(candidate) { return candidate.id === item.id; });
              Renderer.selectItem(newIndex);
            });

            var playIcon = document.createElement('span');
            playIcon.className = 'play-icon';
            playIcon.setAttribute('aria-hidden', 'true');
            playIcon.textContent = '▶';

            var lessonTitle = document.createElement('span');
            lessonTitle.className = 'lesson-title';
            lessonTitle.textContent = item.title || item.original_filename || 'Audio';

            var lessonStatus = document.createElement('span');
            lessonStatus.className = 'lesson-status';
            lessonStatus.textContent = item.status || 'unknown';

            var completionDot = document.createElement('span');
            completionDot.className = 'completion-dot';
            completionDot.setAttribute('aria-hidden', 'true');

            button.append(playIcon, lessonTitle, lessonStatus, completionDot);
            list.appendChild(button);
          })(items[ii]);
        }

        // Level-toggle collapse/expand behavior
        (function(toggleBtn, plusSpan, listEl) {
          toggleBtn.addEventListener('click', function() {
            var expanded = toggleBtn.getAttribute('aria-expanded') === 'true';
            toggleBtn.setAttribute('aria-expanded', String(!expanded));
            plusSpan.textContent = expanded ? '+' : '−';
            listEl.hidden = expanded;
          });
        })(toggle, plus, list);

        section.append(toggle, list);
        menu.appendChild(section);
      }

      // Inject .search-empty paragraph when filtered is empty
      if (filtered.length === 0) {
        var emptyP = document.createElement('p');
        emptyP.className = 'search-empty';
        emptyP.textContent = 'No lessons match your search.';
        menu.appendChild(emptyP);
      }
    },

    selectItem: function(index) {
      if (index < 0 || index >= State.filtered.length) return;
      State.selectedIndex = index;
      var item = State.filtered[index];

      // Show hero-content, hide hero-empty
      var heroContent = document.getElementById('hero-content');
      var heroEmpty = document.getElementById('hero-empty');
      if (heroContent) heroContent.hidden = false;
      if (heroEmpty) heroEmpty.hidden = true;

      // Populate title, subtitle, statusBadge
      if (title) title.textContent = item.title || item.original_filename || 'Untitled audio';
      if (subtitle) subtitle.textContent = (levelLabels[item.level] || item.level) + ' · ' + (item.original_filename || '');
      if (statusBadge) {
        statusBadge.textContent = item.status || 'unknown';
        statusBadge.className = badgeClass(item.status);
      }
      displaySpeakerBadge(item);
      if (voiceRecommendation) {
        voiceRecommendation.textContent = getVoiceRecommendation(item, State.catalog);
      }

      // Show panel skeletons then immediately populate (synchronous)
      SkeletonHelper.showPanels();

      // Populate panels using resolveText() from lib.js
      if (lvText) lvText.textContent = resolveText(item.lv_text, 'lv');
      if (enText) enText.textContent = resolveText(item.en_text, 'en');

      SkeletonHelper.hidePanels();

      // Show/hide Markdown links via hidden attribute
      if (lvLink) {
        if (item.lv_markdown_url) {
          lvLink.href = item.lv_markdown_url;
          lvLink.hidden = false;
        } else {
          lvLink.hidden = true;
        }
      }
      if (enLink) {
        if (item.en_markdown_url) {
          enLink.href = item.en_markdown_url;
          enLink.hidden = false;
        } else {
          enLink.hidden = true;
        }
      }

      // Set audio src
      if (audio) {
        audio.preload = 'metadata';
        audio.src = audioSource.getAudioUrl(item.audio_url || '');
      }

      AudioController.loadWaveform(item.waveform_url || audioSource.getWaveformUrl(item.audio_url || ''));

      // Update prev/next button disabled state
      if (previousButton) previousButton.disabled = State.selectedIndex <= 0;
      if (nextButton) nextButton.disabled = State.selectedIndex >= State.filtered.length - 1;

      // Re-render menu to reflect new active state
      Renderer.renderMenu(
        State.filtered,
        State.selectedIndex,
        ProgressTracker ? ProgressTracker.getCompleted() : {}
      );
      renderComprehensionMeter(item.lv_text || '');
      if (lvText) lvText.innerHTML = renderTranscriptWithClickableSentences(item.lv_text || '');

      if (ShadowingMode.tabShadowing && ShadowingMode.tabShadowing.classList.contains('active')) {
        ShadowingMode.initForCurrentItem();
      }
    },

    renderEmptyState: function(type) {
      if (type === 'catalog-error') {
        // Hide .player-card and both .text-panel elements
        var playerCard = document.querySelector('.player-card');
        if (playerCard) playerCard.hidden = true;
        var textPanels = document.querySelectorAll('.text-panel');
        textPanels.forEach(function(el) { el.hidden = true; });

        // Show error message in #hero-empty
        var heroEmpty = document.getElementById('hero-empty');
        var heroContent = document.getElementById('hero-content');
        if (heroContent) heroContent.hidden = true;
        if (heroEmpty) {
          heroEmpty.hidden = false;
          // Update the heading to show the error message
          var heading = heroEmpty.querySelector('h2');
          if (heading) heading.textContent = 'Catalog not ready. Run the build script after processing audio.';
          var para = heroEmpty.querySelector('p');
          if (para) para.hidden = true;
          var ctas = heroEmpty.querySelector('.hero-ctas');
          if (ctas) ctas.hidden = true;
        }
      }
    }
  };

  // ---------------------------------------------------------------------------
  // ShadowingMode — pronunciation practice with sentence-by-sentence playback
  // ---------------------------------------------------------------------------
  var ShadowingMode = {
    sentences: [],
    currentIndex: 0,
    isRecording: false,
    mediaRecorder: null,
    audioChunks: [],
    userAudioBlob: null,
    userAudioUrl: null,
    audioContext: null,
    analyser: null,
    animationId: null,
    recognition: null,
    SpeechRecognition: window.SpeechRecognition || window.webkitSpeechRecognition,

    init: function() {
      this.tabTranscript = document.getElementById('tab-transcript');
      this.tabShadowing = document.getElementById('tab-shadowing');
      this.transcriptView = document.getElementById('transcript-view');
      this.shadowingView = document.getElementById('shadowing-view');
      this.currentSentenceEl = document.getElementById('currentSentence');
      this.currentTranslationEl = document.getElementById('currentTranslation');
      this.sentenceCounter = document.getElementById('sentenceCounter');
      this.showTranslation = document.getElementById('showTranslation');
      this.prevBtn = document.getElementById('shadowPrev');
      this.replayBtn = document.getElementById('shadowReplay');
      this.recordBtn = document.getElementById('shadowRecord');
      this.stopBtn = document.getElementById('shadowStop');
      this.playRecordingBtn = document.getElementById('shadowPlayRecording');
      this.nextBtn = document.getElementById('shadowNext');
      this.waveformCanvas = document.getElementById('waveformCanvas');
      this.recordingStatus = document.getElementById('recordingStatus');
      this.feedbackEl = document.getElementById('pronunciationFeedback');

      if (this.tabTranscript) {
        this.tabTranscript.addEventListener('click', () => this.showTranscriptTab());
      }
      if (this.tabShadowing) {
        this.tabShadowing.addEventListener('click', () => this.showShadowingTab());
      }
      if (this.showTranslation) {
        this.showTranslation.addEventListener('change', () => this.toggleTranslation());
      }
      if (this.prevBtn) this.prevBtn.addEventListener('click', () => this.prevSentence());
      if (this.replayBtn) this.replayBtn.addEventListener('click', () => this.playCurrentSentence());
      if (this.recordBtn) this.recordBtn.addEventListener('click', () => this.startRecording());
      if (this.stopBtn) this.stopBtn.addEventListener('click', () => this.stopRecording());
      if (this.playRecordingBtn) this.playRecordingBtn.addEventListener('click', () => this.playUserRecording());
      if (this.nextBtn) this.nextBtn.addEventListener('click', () => this.nextSentence());
    },

    showTranscriptTab: function() {
      if (!this.tabTranscript || !this.tabShadowing || !this.transcriptView || !this.shadowingView) return;
      this.tabTranscript.classList.add('active');
      this.tabShadowing.classList.remove('active');
      this.transcriptView.classList.remove('hidden');
      this.shadowingView.classList.add('hidden');
    },

    showShadowingTab: function() {
      if (!this.tabTranscript || !this.tabShadowing || !this.transcriptView || !this.shadowingView) return;
      this.tabShadowing.classList.add('active');
      this.tabTranscript.classList.remove('active');
      this.transcriptView.classList.add('hidden');
      this.shadowingView.classList.remove('hidden');
      this.initForCurrentItem();
    },

    toggleTranslation: function() {
      if (this.currentTranslationEl) {
        this.currentTranslationEl.classList.toggle('hidden', !this.showTranslation.checked);
      }
    },

    splitIntoSentences: function(text) {
      if (!text) return [];
      var sentenceRegex = /[^.!?]+[.!?]+/g;
      var matches = text.match(sentenceRegex);
      if (!matches) return text ? [text] : [];
      return matches.map(function(s) { return s.trim(); }).filter(function(s) { return s.length > 0; });
    },

    initForCurrentItem: function() {
      var item = State.filtered[State.selectedIndex];
      if (!item || !item.lv_text) {
        if (this.currentSentenceEl) this.currentSentenceEl.textContent = 'No transcript available for shadowing.';
        if (this.currentTranslationEl) this.currentTranslationEl.textContent = '';
        if (this.sentenceCounter) this.sentenceCounter.textContent = '0 / 0';
        this.sentences = [];
        this.updateControls();
        return;
      }

      this.sentences = this.splitIntoSentences(item.lv_text);
      this.currentIndex = 0;
      this.userAudioBlob = null;
      this.userAudioUrl = null;
      if (this.recordingStatus) this.recordingStatus.textContent = '';
      if (this.feedbackEl) this.feedbackEl.textContent = '';
      this.clearWaveform();

      if (this.sentences.length > 0) {
        this.displayCurrentSentence();
      } else {
        if (this.currentSentenceEl) this.currentSentenceEl.textContent = 'No sentences found in transcript.';
        if (this.sentenceCounter) this.sentenceCounter.textContent = '0 / 0';
      }
      this.updateControls();
    },

    displayCurrentSentence: function() {
      if (this.sentences.length === 0) return;
      if (this.currentSentenceEl) this.currentSentenceEl.textContent = this.sentences[this.currentIndex];
      if (this.sentenceCounter) this.sentenceCounter.textContent = (this.currentIndex + 1) + ' / ' + this.sentences.length;

      var item = State.filtered[State.selectedIndex];
      if (item && item.en_text && this.currentTranslationEl) {
        var enSentences = this.splitIntoSentences(item.en_text);
        this.currentTranslationEl.textContent = enSentences[this.currentIndex] || '';
      }

      this.updateControls();
    },

    updateControls: function() {
      var hasSentences = this.sentences.length > 0;
      if (this.prevBtn) this.prevBtn.disabled = !hasSentences || this.currentIndex === 0;
      if (this.replayBtn) this.replayBtn.disabled = !hasSentences;
      if (this.recordBtn) this.recordBtn.disabled = !hasSentences || this.isRecording;
      if (this.stopBtn) this.stopBtn.disabled = !this.isRecording;
      if (this.playRecordingBtn) this.playRecordingBtn.disabled = !hasSentences || !this.userAudioUrl;
      if (this.nextBtn) this.nextBtn.disabled = !hasSentences || this.currentIndex >= this.sentences.length - 1;
    },

    playCurrentSentence: function() {
      if (this.sentences.length === 0) return;
      var sentenceText = this.sentences[this.currentIndex];
      var utterance = new SpeechSynthesisUtterance(sentenceText);
      utterance.lang = 'lv-LV';
      utterance.rate = 0.8;
      speechSynthesis.speak(utterance);
    },

    prevSentence: function() {
      if (this.currentIndex > 0) {
        this.currentIndex--;
        this.displayCurrentSentence();
        this.userAudioBlob = null;
        this.userAudioUrl = null;
        if (this.recordingStatus) this.recordingStatus.textContent = '';
        if (this.feedbackEl) this.feedbackEl.textContent = '';
        this.clearWaveform();
      }
    },

    nextSentence: function() {
      if (this.currentIndex < this.sentences.length - 1) {
        this.currentIndex++;
        this.displayCurrentSentence();
        this.userAudioBlob = null;
        this.userAudioUrl = null;
        if (this.recordingStatus) this.recordingStatus.textContent = '';
        if (this.feedbackEl) this.feedbackEl.textContent = '';
        this.clearWaveform();
      }
    },

    startRecording: function() {
      var self = this;
      if (this.isRecording) return;

      navigator.mediaDevices.getUserMedia({ audio: true }).then(function(stream) {
        self.mediaRecorder = new MediaRecorder(stream);
        self.audioChunks = [];
        self.isRecording = true;

        self.mediaRecorder.ondataavailable = function(event) {
          self.audioChunks.push(event.data);
        };

        self.mediaRecorder.onstop = function() {
          self.userAudioBlob = new Blob(self.audioChunks, { type: 'audio/webm' });
          if (self.userAudioUrl) URL.revokeObjectURL(self.userAudioUrl);
          self.userAudioUrl = URL.createObjectURL(self.userAudioBlob);
          if (self.recordingStatus) self.recordingStatus.textContent = 'Recording saved for self-review.';

          if (self.SpeechRecognition) {
            self.tryRecognition();
          }

          stream.getTracks().forEach(function(track) { track.stop(); });
          self.updateControls();
        };

        self.mediaRecorder.start();
        if (self.recordingStatus) self.recordingStatus.textContent = 'Recording...';
        self.updateControls();
        self.visualizeAudio(stream);
      }).catch(function(err) {
        console.error('Microphone error:', err);
        if (err.name === 'NotAllowedError') {
          if (self.recordingStatus) self.recordingStatus.textContent = 'Microphone permission denied. Please allow access to record.';
        } else {
          if (self.recordingStatus) self.recordingStatus.textContent = 'Could not access microphone.';
        }
      });
    },

    stopRecording: function() {
      var self = this;
      if (this.mediaRecorder && this.isRecording) {
        this.mediaRecorder.stop();
        this.isRecording = false;
        if (this.animationId) {
          cancelAnimationFrame(this.animationId);
          this.animationId = null;
        }
      }
    },

    playUserRecording: function() {
      if (this.userAudioUrl) {
        var playAudio = new Audio(this.userAudioUrl);
        playAudio.play();
      }
    },

    visualizeAudio: function(stream) {
      var self = this;
      if (!this.audioContext) {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
      }
      this.analyser = this.audioContext.createAnalyser();
      var source = this.audioContext.createMediaStreamSource(stream);
      source.connect(this.analyser);
      this.analyser.fftSize = 256;

      var bufferLength = this.analyser.frequencyBinCount;
      var dataArray = new Uint8Array(bufferLength);
      var ctx = this.waveformCanvas.getContext('2d');

      function draw() {
        if (!self.isRecording) return;
        self.animationId = requestAnimationFrame(draw);
        self.analyser.getByteFrequencyData(dataArray);

        ctx.fillStyle = '#e7eff3';
        ctx.fillRect(0, 0, self.waveformCanvas.width, self.waveformCanvas.height);

        var barWidth = (self.waveformCanvas.width / bufferLength) * 2.5;
        var x = 0;
        for (var i = 0; i < bufferLength; i++) {
          var barHeight = (dataArray[i] / 255) * self.waveformCanvas.height;
          ctx.fillStyle = 'rgb(214, 10, 79)';
          ctx.fillRect(x, self.waveformCanvas.height - barHeight, barWidth, barHeight);
          x += barWidth + 1;
        }
      }

      draw();
    },

    clearWaveform: function() {
      if (!this.waveformCanvas) return;
      var ctx = this.waveformCanvas.getContext('2d');
      ctx.fillStyle = '#e7eff3';
      ctx.fillRect(0, 0, this.waveformCanvas.width, this.waveformCanvas.height);
    },

    tryRecognition: function() {
      var self = this;
      if (!this.SpeechRecognition) {
        if (this.feedbackEl) this.feedbackEl.textContent = '';
        return;
      }

      this.recognition = new this.SpeechRecognition();
      this.recognition.lang = 'lv-LV';
      this.recognition.interimResults = false;
      this.recognition.maxAlternatives = 1;

      this.recognition.onresult = function(event) {
        var transcript = event.results[0][0].transcript;
        var targetSentence = self.sentences[self.currentIndex];
        var similarity = self.calculateSimilarity(transcript.toLowerCase(), targetSentence.toLowerCase());

        var feedback = 'You said: ' + transcript + '<br>';
        if (similarity > 0.7) {
          feedback += '<span class="feedback-good">Great match! (' + Math.round(similarity * 100) + '%)</span>';
        } else if (similarity > 0.4) {
          feedback += '<span class="feedback-ok">Partial match (' + Math.round(similarity * 100) + '%). Try again!</span>';
        } else {
          feedback += '<span class="feedback-low">Keep practicing! (' + Math.round(similarity * 100) + '%)</span>';
        }
        if (self.feedbackEl) self.feedbackEl.innerHTML = feedback;
      };

      this.recognition.onerror = function(event) {
        console.error('Speech recognition error:', event.error);
        if (self.feedbackEl) self.feedbackEl.innerHTML = 'Speech recognition unavailable. Recording saved for self-review.';
      };

      if (this.userAudioBlob) {
        this.recognition.start();
      }
    },

    calculateSimilarity: function(str1, str2) {
      var words1 = str1.replace(/[^\w\s]/g, '').toLowerCase().split(/\s+/).filter(function(w) { return w; });
      var words2 = str2.replace(/[^\w\s]/g, '').toLowerCase().split(/\s+/).filter(function(w) { return w; });

      if (words1.length === 0 || words2.length === 0) return 0;

      var set2 = {};
      words2.forEach(function(w) { set2[w] = true; });
      var matches = 0;
      for (var i = 0; i < words1.length; i++) {
        if (set2[words1[i]]) matches++;
      }

      return (2 * matches) / (words1.length + words2.length);
    }
  };

  ShadowingMode.init();

  // ---------------------------------------------------------------------------
  // AudioController — custom audio player, waveform, and sticky player
  // ---------------------------------------------------------------------------
  var AudioController = {
    init: function() {
      var playPauseBtn = document.getElementById('play-pause');
      var seekBar = document.getElementById('seek-bar');
      var audioErrorEl = document.getElementById('audio-error');
      var playbackStatus = document.getElementById('playback-status');

      if (playPauseBtn) {
        playPauseBtn.addEventListener('click', function() {
          if (audio.paused) {
            AudioController.play();
          } else {
            AudioController.pause();
          }
        });
      }

      if (seekBar) {
        seekBar.addEventListener('input', function() {
          AudioController.seek(seekBar.value / 100);
        });
        seekBar.addEventListener('keydown', function(e) {
          if (e.key === 'ArrowRight') {
            e.preventDefault();
            audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 1);
          } else if (e.key === 'ArrowLeft') {
            e.preventDefault();
            audio.currentTime = Math.max(0, audio.currentTime - 1);
          }
        });
      }

      if (audio) {
        audio.addEventListener('timeupdate', function() {
          AudioController.updateUI();
        });
        audio.addEventListener('ended', function() {
          State.isPlaying = false;
          var item = State.filtered[State.selectedIndex];
          if (item) {
            analyticsTracker.track(Analytics.EventTypes.LESSON_COMPLETE, {
              lesson_id: item.id,
              filename: item.original_filename
            });
          }
          AudioController.updateUI();
          if (playbackStatus) playbackStatus.textContent = 'Track ended';
        });
        audio.addEventListener('error', function() {
          if (audioErrorEl) audioErrorEl.hidden = false;
          if (playPauseBtn) playPauseBtn.disabled = true;
          if (playbackStatus) playbackStatus.textContent = 'Audio failed to load.';
        });
      }

      AudioController.initStickyPlayer();
    },

    play: function() {
      if (audio) {
        audio.play().catch(function() {});
        State.isPlaying = true;
        AudioController.updateUI();
        var playbackStatus = document.getElementById('playback-status');
        if (playbackStatus) playbackStatus.textContent = 'Playing';
      }
    },

    pause: function() {
      if (audio) {
        audio.pause();
        State.isPlaying = false;
        AudioController.updateUI();
        var playbackStatus = document.getElementById('playback-status');
        if (playbackStatus) playbackStatus.textContent = 'Paused';
      }
    },

    seek: function(ratio) {
      if (audio && audio.duration) {
        audio.currentTime = ratio * audio.duration;
      }
    },

    updateUI: function() {
      var playPauseBtn = document.getElementById('play-pause');
      var seekBar = document.getElementById('seek-bar');
      var timeDisplay = document.getElementById('time-display');
      var stickyPlayPause = document.getElementById('sticky-play-pause');
      var stickySeek = document.getElementById('sticky-seek');
      var stickyTime = document.getElementById('sticky-time');

      var currentTime = audio ? audio.currentTime : 0;
      var duration = audio ? (audio.duration || 0) : 0;
      var progress = duration > 0 ? (currentTime / duration) * 100 : 0;
      var paused = audio ? audio.paused : true;

      State.currentTime = currentTime;
      State.duration = duration;

      if (seekBar) seekBar.value = progress;
      if (timeDisplay) timeDisplay.textContent = formatTime(currentTime) + ' / ' + formatTime(duration);
      if (playPauseBtn) {
        playPauseBtn.setAttribute('aria-label', paused ? 'Play' : 'Pause');
        var icon = playPauseBtn.querySelector('.icon-play');
        if (icon) icon.textContent = paused ? '▶' : '⏸';
      }

      // Mirror to sticky player
      if (stickySeek) stickySeek.value = progress;
      if (stickyTime) stickyTime.textContent = formatTime(currentTime);
      if (stickyPlayPause) {
        stickyPlayPause.setAttribute('aria-label', paused ? 'Play' : 'Pause');
        var stickyIcon = stickyPlayPause.querySelector('.icon-play');
        if (stickyIcon) stickyIcon.textContent = paused ? '▶' : '⏸';
      }
    },

    loadWaveform: function(url) {
      if (!url) return;
      var canvas = document.getElementById('waveform-canvas');
      if (!canvas) return;
      fetch(url)
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(data) {
          if (!Array.isArray(data) || data.length === 0) return;
          State.waveformData = data;
          var ctx = canvas.getContext('2d');
          var w = canvas.offsetWidth || canvas.width;
          var h = canvas.offsetHeight || canvas.height;
          canvas.width = w;
          canvas.height = h;
          ctx.clearRect(0, 0, w, h);
          ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim() || '#d60a4f';
          var barWidth = Math.max(1, Math.floor(w / data.length));
          for (var i = 0; i < data.length; i++) {
            var barH = Math.round(data[i] * h);
            ctx.fillRect(i * barWidth, h - barH, barWidth - 1, barH);
          }
        })
        .catch(function(e) { console.warn('Waveform load failed:', e); });
    },

    initStickyPlayer: function() {
      var stickyPlayer = document.getElementById('sticky-player');
      var playerCard = document.querySelector('.player-card');
      var stickyPlayPause = document.getElementById('sticky-play-pause');
      var stickySeek = document.getElementById('sticky-seek');

      if (!stickyPlayer || !playerCard) return;

      // Wire sticky controls
      if (stickyPlayPause) {
        stickyPlayPause.addEventListener('click', function() {
          if (audio && audio.paused) {
            AudioController.play();
          } else {
            AudioController.pause();
          }
        });
      }
      if (stickySeek) {
        stickySeek.addEventListener('input', function() {
          AudioController.seek(stickySeek.value / 100);
        });
      }

      // IntersectionObserver: show sticky player when player-card is out of view on mobile
      if ('IntersectionObserver' in window) {
        var observer = new IntersectionObserver(function(entries) {
          var isMobile = window.innerWidth <= 768;
          entries.forEach(function(entry) {
            if (isMobile && !entry.isIntersecting) {
              stickyPlayer.hidden = false;
            } else {
              stickyPlayer.hidden = true;
            }
          });
        }, { threshold: 0 });
        observer.observe(playerCard);
      }
    }
  };

  // ---------------------------------------------------------------------------
  // SearchHandler — debounced search input handling
  // ---------------------------------------------------------------------------
  var SearchHandler = {
    _timer: null,
    init: function() {
      var searchInput = document.getElementById('search');
      if (!searchInput) return;
      searchInput.addEventListener('input', function() {
        clearTimeout(SearchHandler._timer);
        SearchHandler._timer = setTimeout(function() {
          applyCombinedFilters();
        }, 300);
      });
    }
  };

  // ---------------------------------------------------------------------------
  // Event wiring
  // ---------------------------------------------------------------------------
  previousButton.addEventListener('click', function () { Renderer.selectItem(State.selectedIndex - 1); });
  nextButton.addEventListener('click', function () { Renderer.selectItem(State.selectedIndex + 1); });
  SearchHandler.init();
  if (styleFilter) {
    styleFilter.addEventListener('change', applyCombinedFilters);
  }
  if (categoryFilter) {
    categoryFilter.addEventListener('change', function() {
      updateURLWithCategory(categoryFilter.value);
      applyCombinedFilters();
    });
  }

  var brandSection = document.querySelector('.brand');
  if (brandSection) {
    var modeButton = document.createElement('button');
    modeButton.type = 'button';
    modeButton.className = 'mode-switch-btn';
    modeButton.textContent = currentMode === 'living' ? 'Library' : 'Dzivo Latvija';
    modeButton.addEventListener('click', function() {
      if (currentMode === 'living') {
        currentMode = 'library';
        localStorage.setItem(MODE_KEY, currentMode);
        window.location.reload();
      } else {
        modeButton.textContent = 'Library';
        enterLivingMode();
      }
    });
    brandSection.appendChild(modeButton);
  }

  // Wire theme toggle
  var themeToggleBtn = document.getElementById('theme-toggle');
  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', function () {
      ThemeManager.toggle();
    });
  }

  document.querySelectorAll('.comp-filter-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.comp-filter-btn').forEach(function(other) {
        other.classList.remove('active');
      });
      btn.classList.add('active');
      activeCompFilter = btn.getAttribute('data-filter') || 'all';
      applyCombinedFilters();
    });
  });

(function () {
  // Community Panel initialization
  var panel = document.getElementById("communityPanel");
  var toggle = document.getElementById("communityToggle");
  var closeBtn = document.getElementById("communityClose");
  var tabs = document.querySelectorAll(".community-tabs .tab");
  var entryType = document.getElementById("entryType");
  var authorName = document.getElementById("authorName");
  var entryBody = document.getElementById("entryBody");
  var submitBtn = document.getElementById("submitEntry");
  var sortOrder = document.getElementById("sortOrder");
  var listEl = document.getElementById("communityList");

  var currentTab = "questions";
  var currentLessonId = null;

  function getLessonId() {
    if (State.filtered[State.selectedIndex]) {
      return State.filtered[State.selectedIndex].id;
    }
    return "default";
  }

  function getEntryType() {
    var typeMap = {
      questions: "question",
      comments: "comment",
      translations: "translation_suggestion",
    };
    return typeMap[currentTab];
  }

  function renderEntry(entry) {
    var div = document.createElement("div");
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

  // AI Panel event listeners (from main)
  if (closeAIPanelBtn) closeAIPanelBtn.addEventListener('click', closeAIPanel);
  if (aiOverlay) aiOverlay.addEventListener('click', closeAIPanel);
  if (aiModeToggle && aiService) {
    aiModeToggle.addEventListener('change', function(event) {
      aiService.setExplanationMode(event.target.checked ? 'detailed' : 'simple');
      if (currentExplanationSentence) fetchExplanation(currentExplanationSentence);
    });
  }
  if (retryBtn) {
    retryBtn.addEventListener('click', function() {
      if (currentExplanationSentence) fetchExplanation(currentExplanationSentence);
    });
  }
  if (lvText) {
    lvText.addEventListener('click', function(event) {
      var target = event.target;
      if (!target || !target.classList || !target.classList.contains('sentence-block')) return;
      openAIPanel();
      fetchExplanation(target.textContent || '');
    });
  }

  AudioController.init();

  // ---------------------------------------------------------------------------
  // Category population
  // ---------------------------------------------------------------------------
  function populateCategoryFilter() {
    if (!categoryFilter || !window.CategoryManager) return;
    var categories = CategoryManager.getCategoriesWithCounts(State.catalog);
    var currentValue = categoryFilter.value;
    categoryFilter.innerHTML = '<option value="">All categories</option>';
    categories.forEach(function(cat) {
      if (cat.id === 'uncategorized' && cat.count === 0) return;
      var option = document.createElement('option');
      option.value = cat.id;
      option.textContent = cat.icon + ' ' + cat.title + ' (' + cat.count + ')';
      categoryFilter.appendChild(option);
    });
    var urlParams = new URLSearchParams(window.location.search);
    var urlCategory = urlParams.get('category');
    if (urlCategory) {
      categoryFilter.value = urlCategory;
    } else if (currentValue) {
      categoryFilter.value = currentValue;
    }
  }

  function updateURLWithCategory(categoryId) {
    var url = new URL(window.location.href);
    if (categoryId) {
      url.searchParams.set('category', categoryId);
    } else {
      url.searchParams.delete('category');
    }
    window.history.replaceState({}, '', url);
  }

  function updateCategoryLanding() {
    var heroEmpty = document.getElementById('hero-empty');
    var categoryLanding = document.getElementById('category-landing');
    var categoryCards = document.getElementById('category-cards');
    var heroCtas = document.getElementById('hero-ctas');
    if (!heroEmpty || !categoryLanding || !categoryCards) return;
    if (State.selectedIndex === -1 && window.CategoryManager && State.catalog.length > 0) {
      var categories = CategoryManager.getCategoriesWithCounts(State.catalog).filter(function(c) { return c.id !== 'uncategorized' && c.count > 0; });
      categoryCards.innerHTML = categories.map(function(cat) {
        return '<div class="category-card" data-category="' + cat.id + '">' +
          '<span class="category-icon">' + cat.icon + '</span>' +
          '<span class="category-title">' + cat.title + '</span>' +
          '<span class="category-count">' + cat.count + ' lessons</span>' +
          '<span class="category-desc">' + cat.description + '</span>' +
          '</div>';
      }).join('');
      categoryCards.querySelectorAll('.category-card').forEach(function(card) {
        card.addEventListener('click', function() {
          if (categoryFilter) {
            categoryFilter.value = card.getAttribute('data-category');
            applyCombinedFilters();
          }
        });
      });
      categoryLanding.hidden = false;
      if (heroCtas) heroCtas.hidden = true;
    } else {
      categoryLanding.hidden = true;
      if (heroCtas) heroCtas.hidden = false;
    }
  }

  var btnBrowseCategory = document.getElementById('btn-browse-category');
  if (btnBrowseCategory) {
    btnBrowseCategory.addEventListener('click', function() {
      updateCategoryLanding();
    });
  }

  // ---------------------------------------------------------------------------
  // Catalog fetch
  // ---------------------------------------------------------------------------
  SkeletonHelper.showSidebar();
  fetch('catalog.json', { cache: 'no-store' })
    .then(function (response) {
      if (!response.ok) throw new Error('Catalog request failed: ' + response.status);
      return response.json();
    })
    .then(function (items) {
      var validation = LessonValidation.validateCatalog(items, isDev);
      if (!validation.valid) {
        console.warn('[Catalog] Lesson data validation failed:', validation.errors);
      }
      State.catalog = Array.isArray(items) ? items : [];
      State.filtered = filterByComprehension(State.catalog.slice());
      SkeletonHelper.hideSidebar();
      populateCategoryFilter();
      updateCategoryLanding();
      if (currentMode === 'living') {
        enterLivingMode();
        return;
      }
      Renderer.renderMenu(
        State.filtered,
        State.selectedIndex,
        ProgressTracker ? ProgressTracker.getCompleted() : {}
      );
      if (State.filtered.length) {
        Renderer.selectItem(0);
      }
    })
    .catch(function (error) {
      console.error(error);
      State.filtered = [];
      Renderer.renderEmptyState('catalog-error');
    });

  // ---------------------------------------------------------------------------
  // Expose test hooks
  // ---------------------------------------------------------------------------
  window.__lll = {
    selectItem: function(index) { Renderer.selectItem(index); },
    State: State,
    ProgressTracker: ProgressTracker,
    ThemeManager: ThemeManager,
    Analytics: analyticsTracker
  };
  window.analytics = analyticsTracker;

  // ---------------------------------------------------------------------------
  // InteractiveListeningMode — sentence highlighting, speed controls, cloze
  // ---------------------------------------------------------------------------
  var InteractiveListeningMode = {
    sentences: [],
    currentSentenceIndex: -1,
    isTranscriptVisible: true,
    clozeWords: [],
    clozeUserAnswers: [],

    init: function() {
      this.setupSpeedControls();
      this.setupHideTranscript();
      this.setupSentenceClickEvents();
      this.setupAudioTimeUpdate();
      this.setupClozeExercises();
    },

    setupSpeedControls: function() {
      var speedBtn = document.getElementById('speed-btn');
      var speedMenu = document.getElementById('speed-menu');
      var audio = document.querySelector('#audio');
      if (!speedBtn || !speedMenu || !audio) return;

      speedBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        speedMenu.classList.toggle('hidden');
      });

      speedMenu.querySelectorAll('.speed-option').forEach(function(btn) {
        btn.addEventListener('click', function() {
          var speed = parseFloat(btn.getAttribute('data-speed'));
          audio.playbackRate = speed;
          speedBtn.textContent = speed + 'x';
          speedMenu.classList.add('hidden');
        });
      });

      document.addEventListener('click', function() {
        if (!speedMenu.classList.contains('hidden')) {
          speedMenu.classList.add('hidden');
        }
      });
    },

    setupHideTranscript: function() {
      var hideBtn = document.getElementById('hide-transcript-btn');
      var lvTextEl = document.getElementById('lvText');
      var enTextEl = document.getElementById('enText');
      if (!hideBtn || !lvTextEl) return;

      hideBtn.addEventListener('click', function() {
        this.isTranscriptVisible = !this.isTranscriptVisible;
        lvTextEl.style.display = this.isTranscriptVisible ? '' : 'none';
        if (enTextEl) enTextEl.style.display = this.isTranscriptVisible ? '' : 'none';
        hideBtn.textContent = this.isTranscriptVisible ? '👁️' : '👁️‍🗨️';
      }.bind(this));
    },

    setupSentenceClickEvents: function() {
      var self = this;
      document.addEventListener('click', function(e) {
        var target = e.target;
        if (target.classList.contains('sentence-block')) {
          var index = parseInt(target.getAttribute('data-sentence'), 10);
          self.highlightSentence(index);
        }
      });
    },

    setupAudioTimeUpdate: function() {
      var audio = document.querySelector('#audio');
      var self = this;
      if (!audio) return;

      audio.addEventListener('timeupdate', function() {
        if (self.sentences.length === 0) return;
        var currentTime = audio.currentTime;
        for (var i = 0; i < self.sentences.length; i++) {
          var sent = self.sentences[i];
          if (currentTime >= sent.start && currentTime < sent.end) {
            if (self.currentSentenceIndex !== i) {
              self.highlightSentence(i);
            }
            return;
          }
        }
      });
    },

    parseSentences: function(text) {
      if (!text) return [];
      var rawSentences = text.split(/(?<=[.!?])\s+/);
      var sentences = [];
      var totalDuration = 0;
      var audio = document.querySelector('#audio');
      var duration = audio ? audio.duration : 180;

      rawSentences.forEach(function(sent, i) {
        sent = sent.trim();
        if (sent.length > 0) {
          var avgWordDuration = duration / Math.max(1, sent.split(/\s+/).length);
          sentences.push({
            index: i,
            text: sent,
            start: totalDuration,
            end: totalDuration + avgWordDuration * sent.split(/\s+/).length
          });
          totalDuration += avgWordDuration * sent.split(/\s+/).length;
        }
      });
      return sentences;
    },

    highlightSentence: function(index) {
      var blocks = document.querySelectorAll('.sentence-block');
      blocks.forEach(function(block) { block.classList.remove('active-sentence'); });
      var activeBlock = document.querySelector('.sentence-block[data-sentence="' + index + '"]');
      if (activeBlock) {
        activeBlock.classList.add('active-sentence');
        activeBlock.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      this.currentSentenceIndex = index;
    },

    setupClozeExercises: function() {
      var checkBtn = document.getElementById('checkClozeBtn');
      var resetBtn = document.getElementById('resetClozeBtn');
      var self = this;

      if (checkBtn) checkBtn.addEventListener('click', function() { self.checkClozeAnswers(); });
      if (resetBtn) resetBtn.addEventListener('click', function() { self.generateCloze(); });
    },

    generateCloze: function() {
      var item = State.filtered[State.selectedIndex];
      if (!item || !item.lv_text) return;

      var text = item.lv_text;
      var words = text.split(/\s+/).filter(function(w) { return w.length > 3; });
      var stopwords = ['un', 'un', 'bet', 'vai', 'ir', 'bija', 'būs', 'nav', 'būt', 'ka', 'lai', 'kas', 'kur', 'kad', 'kā', 'jo', 'līdz', 'par', 'pēc'];
      var candidateWords = words.filter(function(w) {
        var clean = w.replace(/[.,!?;:"''()[\]{}]/g, '').toLowerCase();
        return stopwords.indexOf(clean) === -1 && clean.length > 3;
      });

      var numToHide = Math.min(5, Math.max(3, Math.floor(candidateWords.length * 0.15)));
      var shuffled = candidateWords.slice().sort(function() { return Math.random() - 0.5; });
      this.clozeWords = shuffled.slice(0, numToHide);
      this.clozeUserAnswers = new Array(numToHide).fill('');

      var clozeContainer = document.getElementById('clozeContainer');
      var clozeSection = document.getElementById('clozeSection');
      if (!clozeContainer || !clozeSection) return;

      clozeSection.style.display = 'block';
      clozeContainer.innerHTML = '';

      var displayText = text;
      this.clozeWords.forEach(function(word, i) {
        var clean = word.replace(/[.,!?;:"''()[\]{}]/g, '');
        var regex = new RegExp('\\b' + clean + '\\b', 'gi');
        displayText = displayText.replace(regex, '<input type="text" class="cloze-input" data-index="' + i + '" placeholder="..." aria-label="Missing word ' + (i+1) + '">');
      });

      clozeContainer.innerHTML = '<div class="cloze-text">' + displayText + '</div>';

      clozeContainer.querySelectorAll('.cloze-input').forEach(function(input) {
        input.addEventListener('input', function() {
          var idx = parseInt(this.getAttribute('data-index'), 10);
          self.clozeUserAnswers[idx] = this.value.toLowerCase();
        });
      });

      document.getElementById('clozeProgress').textContent = '0/' + this.clozeWords.length;
    },

    checkClozeAnswers: function() {
      var correct = 0;
      var inputs = document.querySelectorAll('.cloze-input');

      this.clozeWords.forEach(function(word, i) {
        var clean = word.replace(/[.,!?;:"''()[\]{}]/g, '').toLowerCase();
        var input = inputs[i];
        if (!input) return;

        var userAnswer = this.clozeUserAnswers[i] || '';
        var isCorrect = userAnswer.trim() === clean;

        input.classList.remove('correct', 'incorrect');
        input.classList.add(isCorrect ? 'correct' : 'incorrect');
        if (isCorrect) correct++;
      }.bind(this));

      document.getElementById('clozeProgress').textContent = correct + '/' + this.clozeWords.length + ' correct';
    },

    onLessonSelect: function(item) {
      this.sentences = this.parseSentences(item.lv_text || '');
      this.generateCloze();
    }
  };

  // Initialize interactive listening when lesson is selected
  var originalSelectItem = window.__lll && window.__lll.selectItem;
  if (originalSelectItem) {
    var wrappedSelectItem = function(index) {
      originalSelectItem(index);
      var item = State.filtered[index];
      if (item) InteractiveListeningMode.onLessonSelect(item);
    };
    window.__lll.selectItem = wrappedSelectItem;
  }

  // Also hook into existing selectItem function by patching Renderer.selectItem
  if (Renderer && Renderer.selectItem) {
    var originalRendererSelectItem = Renderer.selectItem;
    Renderer.selectItem = function(index) {
      originalRendererSelectItem.apply(this, arguments);
      var item = State.filtered[index];
      if (item) InteractiveListeningMode.onLessonSelect(item);
    };
  }

  // Initialize on page load
  document.addEventListener('DOMContentLoaded', function() {
    InteractiveListeningMode.init();
  });

  // ---------------------------------------------------------------------------
  // CulturalContextManager — display cultural context cards for lessons
  // ---------------------------------------------------------------------------
  var CulturalContextManager = {
    contexts: null,
    currentLessonId: null,

    loadContexts: function() {
      var self = this;
      return fetch('contexts.json')
        .then(function(response) { return response.json(); })
        .then(function(data) {
          self.contexts = data;
          return data;
        })
        .catch(function() {
          self.contexts = [];
          return [];
        });
    },

    getContextsForLesson: function(lessonId) {
      if (!this.contexts) return [];
      return this.contexts.filter(function(ctx) {
        return ctx.lesson_ids && ctx.lesson_ids.indexOf(lessonId) !== -1;
      });
    },

    renderContextCard: function(context) {
      var html = '<div class="cultural-card">';
      html += '<div class="cultural-card-header">';
      html += '<h4>' + escapeHtml(context.title) + '</h4>';
      html += '<span class="cultural-card-badge">' + escapeHtml(context.title_en || '') + '</span>';
      html += '</div>';
      html += '<p class="cultural-explanation">' + escapeHtml(context.explanation) + '</p>';

      if (context.practical_note) {
        html += '<div class="cultural-note">';
        html += '<strong>Practical note:</strong> ' + escapeHtml(context.practical_note);
        html += '</div>';
      }

      if (context.phrases && context.phrases.length > 0) {
        html += '<div class="cultural-phrases">';
        html += '<h5>Useful phrases</h5>';
        context.phrases.forEach(function(phrase) {
          html += '<div class="phrase-item">';
          html += '<span class="phrase-lv">' + escapeHtml(phrase.lv) + '</span>';
          html += '<span class="phrase-en">' + escapeHtml(phrase.en) + '</span>';
          if (phrase.usage) {
            html += '<span class="phrase-usage">' + escapeHtml(phrase.usage) + '</span>';
          }
          html += '</div>';
        });
        html += '</div>';
      }

      html += '</div>';
      return html;
    },

    displayForLesson: function(lessonId) {
      var section = document.getElementById('culturalContextSection');
      var container = document.getElementById('culturalContextList');
      if (!section || !container) return;

      this.currentLessonId = lessonId;
      var contexts = this.getContextsForLesson(lessonId);

      if (contexts.length === 0) {
        section.style.display = 'none';
        return;
      }

      section.style.display = 'block';
      container.innerHTML = contexts.map(function(ctx) {
        return this.renderContextCard(ctx);
      }.bind(this)).join('');
    },

    init: function() {
      var self = this;
      this.loadContexts().then(function() {
        var item = State.filtered[State.selectedIndex];
        if (item) self.displayForLesson(item.id);
      });
    }
  };

  // Hook into lesson selection
  var originalRendererSelectItem2 = Renderer.selectItem;
  Renderer.selectItem = function(index) {
    originalRendererSelectItem2.apply(this, arguments);
    var item = State.filtered[index];
    if (item) CulturalContextManager.displayForLesson(item.id);
  };

  // Initialize on page load
  document.addEventListener('DOMContentLoaded', function() {
    CulturalContextManager.init();
  });

})();
