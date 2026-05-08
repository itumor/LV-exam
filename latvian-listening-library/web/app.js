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

const STORAGE_KEY = "latvian_flashcards";
const STOPWORDS = new Set(["un", "un", "bet", "vai", "ir", "bija", "būs", "ir", "nav", "būt", "ka", "lai", "kas", "kur", "kad", "kā", "jo", "līdz", "par", "pēc", "priekš", "aiz", "uz", "no", "pie", "pa", "pāri", "starp", "ar", "sā", "tā", "arī", "vēl", "jau", "gan", " gan", "tikai", "tomēr", "tad", "ja", "kā", "lai", "lai", "būtu", "var", "varētu", "vajag", "jā", "ne", "nē", "nekad", "nekā", "neko", "nevis", "neviņ", "neviens", "negaidīt", "nestrādā", "nestāv", "nesēž", "neliek", "nemarš", "nebrauc", "neiet", "nav", "nu", "jā", "protams", "žēl", "dieva", "dievs", "žēl", "noteikti", "noteikti", "acīm", "protams", "esot", "tiktu", "tiek", "tik", "tikai", "it"]);

const VOCAB_DICTIONARY = {
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
  const activeTab = document.querySelector('.tab.active');
  if (activeTab && activeTab.id === 'vocabTabBtn') {
    showVocabTab();
  }
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

function extractVocabulary(transcript) {
  if (!transcript) return [];
  const words = transcript.toLowerCase().replace(/[.,!?;:"''()[\]{}]/g, ' ').split(/\s+/).filter(w => w.length > 2 && !STOPWORDS.has(w));
  const wordCounts = {};
  words.forEach(w => { wordCounts[w] = (wordCounts[w] || 0) + 1; });
  return Object.entries(wordCounts).sort((a, b) => b[1] - a[1]).slice(0, 20).map(([word]) => {
    const dictEntry = VOCAB_DICTIONARY[word];
    return { word, en: dictEntry?.en || '—', grammar: dictEntry?.grammar || 'noun', lemma: word };
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
  const deck = loadDeck();
  const now = Date.now();
  return deck.filter(card => card.due <= now);
}

function getMissedCards() {
  const deck = loadDeck();
  return deck.filter(card => card.incorrect > card.correct).sort((a, b) => (b.incorrect - b.correct) - (a.incorrect - a.correct));
}

function addCard(word, en, example, lemma, grammar) {
  const deck = loadDeck();
  if (deck.some(c => c.word === word)) return false;
  deck.push({ word, en, example, lemma, grammar, ease: 2.5, interval: 0, due: Date.now(), correct: 0, incorrect: 0 });
  saveDeck(deck);
  return true;
}

function reviewCard(word, rating) {
  const deck = loadDeck();
  const card = deck.find(c => c.word === word);
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
    }
  })
  .catch((error) => {
    console.error(error);
    filtered = [];
    renderMenu();
    setText(title, "Catalog not ready", "Catalog not ready");
    setText(subtitle, "Run scripts/build_catalog.py after processing audio.", "");
  });
