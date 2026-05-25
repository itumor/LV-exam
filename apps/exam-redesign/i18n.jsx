// i18n.jsx — translation provider for UI chrome.
// The exam content itself (Latvian passages, audio transcripts, answer
// choices, ads) stays in Latvian — that's the language under test. We
// translate everything *around* it: navigation, instructions, intro
// screen, section transitions, result screen.

const { createContext, useContext, useState, useEffect } = React;

const LANGS = [
  { id: "lv", label: "LV", name: "Latviešu" },
  { id: "en", label: "EN", name: "English"  },
  { id: "ru", label: "RU", name: "Русский"  },
];

const STRINGS = {
  // ─── chrome ──────────────────────────────────────────────────
  "chrome.time_remaining": {
    lv: "Atlikušais laiks", en: "Time remaining", ru: "Оставшееся время",
  },
  "chrome.paused": {
    lv: "Apturēts", en: "Paused", ru: "Пауза",
  },
  "chrome.back": {
    lv: "Atpakaļ", en: "Back", ru: "Назад",
  },
  "chrome.next": {
    lv: "Tālāk", en: "Next", ru: "Далее",
  },
  "chrome.end_section": {
    lv: "Beigt daļu", en: "End section", ru: "Завершить раздел",
  },
  "chrome.finish_exam": {
    lv: "Pabeigt eksāmenu", en: "Finish exam", ru: "Завершить экзамен",
  },
  "chrome.start_exam": {
    lv: "Sākt eksāmenu", en: "Start exam", ru: "Начать экзамен",
  },
  "chrome.practice_only": {
    lv: "Tikai praktizēties", en: "Practice mode", ru: "Только тренировка",
  },
  "chrome.foothint.partN": {
    lv: ({ p, n }) => `Daļa ${p} / 4 · uzdevums ${n}`,
    en: ({ p, n }) => `Part ${p} / 4 · task ${n}`,
    ru: ({ p, n }) => `Часть ${p} / 4 · задание ${n}`,
  },
  "chrome.foothint.intro": {
    lv: "Atvēli laiku iepazīties — laiks sāksies, kad turpināsi",
    en: "Take your time to read — the timer starts when you continue",
    ru: "Не торопитесь с инструкцией — таймер начнётся при продолжении",
  },

  // ─── intro screen ────────────────────────────────────────────
  "intro.eyebrow": {
    lv: "VISC · 2024 · Pamata (A2) līmenis",
    en: "VISC · 2024 · Basic (A2) level",
    ru: "VISC · 2024 · Базовый уровень (A2)",
  },
  "intro.title_l1": { lv: "Valsts valodas", en: "Latvian state", ru: "Государственный" },
  "intro.title_l2": { lv: "prasmes pārbaude", en: "language exam",  ru: "языковой экзамен" },
  "intro.lead": {
    lv: ({ b }) => <>Šī ir A2 līmeņa pārbaudes simulācija — četras daļas, 60 punkti kopā. Lai pārbaudi nokārtotu, katrā prasmē jāsasniedz vismaz {b("9 no 15 punktiem")}.</>,
    en: ({ b }) => <>This is a simulation of the A2-level state language exam — four parts, 60 points total. To pass, you must score at least {b("9 of 15 points")} in every skill.</>,
    ru: ({ b }) => <>Это симуляция экзамена A2 по государственному языку — четыре раздела, всего 60 баллов. Чтобы сдать, нужно набрать минимум {b("9 из 15 баллов")} в каждом разделе.</>,
  },
  "intro.disclaimer": {
    lv: "Pārbaudes laikā nedrīkst aizvērt logu. Tehnisku problēmu gadījumā vērsieties pie pārbaudes vadītāja.",
    en: "Do not close this window during the exam. In case of technical issues, contact the proctor.",
    ru: "Не закрывайте окно во время экзамена. При технических неполадках обратитесь к наблюдателю.",
  },
  "intro.rules.title": {
    lv: "Pirms sākam", en: "Before we start", ru: "Перед началом",
  },
  "intro.rules.r1": {
    lv: "Derīgs personu apliecinošs dokuments līdzās",
    en: "A valid ID document at hand",
    ru: "Действующий документ удостоверения личности",
  },
  "intro.rules.r2": {
    lv: "Klusa telpa un austiņas — klausīšanās daļai",
    en: "A quiet room and headphones for the listening part",
    ru: "Тихое помещение и наушники для части аудирования",
  },
  "intro.rules.r3": {
    lv: "Zila vai melna pildspalva — rakstītprasmes daļai",
    en: "A blue or black pen for the writing part",
    ru: "Синяя или чёрная ручка для письменной части",
  },
  "intro.rules.r4": {
    lv: "Pārliecinieties par stabilu interneta savienojumu",
    en: "Make sure your internet connection is stable",
    ru: "Убедитесь в стабильности интернет-соединения",
  },
  "intro.kbdhint.nav": {
    lv: "Navigācija:", en: "Navigate:", ru: "Навигация:",
  },
  "intro.kbdhint.pause": {
    lv: "· apturēt laiku", en: "· pause timer", ru: "· пауза таймера",
  },

  // section thumbnails on intro
  "intro.section.listening.desc": {
    lv: "Seši paziņojumi, viena saruna un piecas īsas sarunas.",
    en: "Six announcements, one dialogue, and five short conversations.",
    ru: "Шесть объявлений, один диалог и пять коротких разговоров.",
  },
  "intro.section.reading.desc": {
    lv: "Četri teksti, divpadsmit sludinājumi un viens cloze tests.",
    en: "Four texts, twelve classified ads, and one cloze test.",
    ru: "Четыре текста, двенадцать объявлений и один тест на пропущенные слова.",
  },
  "intro.section.writing.desc": {
    lv: "Foto albums, vārdu formas un brīva vēstule vai sludinājums.",
    en: "Photo album, word inflections, and a free-form letter or advert.",
    ru: "Фотоальбом, формы слов и свободное письмо или объявление.",
  },
  "intro.section.speaking.desc": {
    lv: "Intervija ar eksaminētāju, attēlu apraksts un trīs jautājumi.",
    en: "Interview with the examiner, an image description, and three questions.",
    ru: "Интервью с экзаменатором, описание изображений и три вопроса.",
  },
  "intro.section.minimum": { lv: "min. 9", en: "min. 9", ru: "мин. 9" },

  // ─── part labels (used in nav + section intro) ──────────────
  "part.listening": { lv: "Klausīšanās",   en: "Listening", ru: "Аудирование" },
  "part.reading":   { lv: "Lasītprasme",   en: "Reading",   ru: "Чтение"     },
  "part.writing":   { lv: "Rakstītprasme", en: "Writing",   ru: "Письмо"     },
  "part.speaking":  { lv: "Runātprasme",   en: "Speaking",  ru: "Говорение"  },
  "part.listening.short": { lv: "Klausīšanās", en: "Listening", ru: "Аудир." },
  "part.reading.short":   { lv: "Lasīšana",    en: "Reading",   ru: "Чтение" },
  "part.writing.short":   { lv: "Rakstīšana",  en: "Writing",   ru: "Письмо" },
  "part.speaking.short":  { lv: "Runāšana",    en: "Speaking",  ru: "Говорение" },

  // ─── section transition screen ──────────────────────────────
  "sect.prev_done": {
    lv: ({ name }) => `${name} pabeigta`,
    en: ({ name }) => `${name} complete`,
    ru: ({ name }) => `${name} завершено`,
  },
  "sect.part_n": {
    lv: "Daļa", en: "Part", ru: "Часть",
  },
  "sect.duration":     { lv: "Ilgums",  en: "Duration", ru: "Время" },
  "sect.points":       { lv: "Punkti",  en: "Points",   ru: "Баллы" },
  "sect.pass":         { lv: "Nokārto", en: "Pass",     ru: "Сдано" },
  "sect.minutes_short":{ lv: "min",     en: "min",      ru: "мин"   },
  "sect.start_cta": {
    lv: ({ part }) => `Sākt ${part.toLowerCase()}`,
    en: ({ part }) => `Begin ${part.toLowerCase()}`,
    ru: ({ part }) => `Начать «${part.toLowerCase()}»`,
  },
  "sect.start_hint": {
    lv: "Laiks sāksies, kad nospiedīsiet pogu",
    en: "The timer starts when you press the button",
    ru: "Таймер запустится при нажатии кнопки",
  },
  "sect.task_word": {
    lv: "uzdevums", en: "Task", ru: "Задание",
  },
  "sect.points_short": {
    lv: ({ n }) => `${n} punkti`,
    en: ({ n }) => `${n} pts`,
    ru: ({ n }) => `${n} баллов`,
  },
  "sect.points_included": {
    lv: "(iekļauts)", en: "(included)", ru: "(включено)",
  },

  // Listening transition
  "sect.listening.heading": { lv: "Klausīšanās prasme", en: "Listening", ru: "Аудирование" },
  "sect.listening.lead":    {
    lv: "Klausieties uzmanīgi. Katrs ieraksts atskanēs divas reizes.",
    en: "Listen carefully. Each recording will play twice.",
    ru: "Слушайте внимательно. Каждая запись прозвучит дважды.",
  },
  "sect.listening.t1.title":{ lv: "1. uzdevums", en: "Task 1", ru: "Задание 1" },
  "sect.listening.t1.body": {
    lv: "6 paziņojumi · multiple choice",
    en: "6 announcements · multiple choice",
    ru: "6 объявлений · с выбором ответа",
  },
  "sect.listening.t2.title":{ lv: "2. uzdevums", en: "Task 2", ru: "Задание 2" },
  "sect.listening.t2.body": {
    lv: "1 saruna · 4 apgalvojumi (Jā/Nē)",
    en: "1 dialogue · 4 statements (Yes/No)",
    ru: "1 диалог · 4 утверждения (Да/Нет)",
  },
  "sect.listening.t3.title":{ lv: "3. uzdevums", en: "Task 3", ru: "Задание 3" },
  "sect.listening.t3.body": {
    lv: "5 īsas sarunas · ievelciet vārdus",
    en: "5 short dialogues · drag the right word",
    ru: "5 коротких диалогов · подставьте слова",
  },
  "sect.listening.tip": {
    lv: "Ja kādu paziņojumu nesaprotat — turpiniet, atbildi varēsiet ievilkt vēlāk.",
    en: "If you don't catch an announcement — keep going, you can fill it in later.",
    ru: "Если вы что-то не расслышали — продолжайте, вернётесь позже.",
  },

  // Reading transition
  "sect.reading.heading": { lv: "Lasītprasme", en: "Reading", ru: "Чтение" },
  "sect.reading.lead": {
    lv: "Vienkārši, ikdienas teksti — sludinājumi, vēstules, raksti.",
    en: "Simple, everyday texts — adverts, letters, articles.",
    ru: "Простые повседневные тексты — объявления, письма, статьи.",
  },
  "sect.reading.t1.title": { lv: "1. uzdevums", en: "Task 1", ru: "Задание 1" },
  "sect.reading.t1.body": {
    lv: "4 teksti · 3 apgalvojumi par katru",
    en: "4 texts · 3 statements about each",
    ru: "4 текста · 3 утверждения к каждому",
  },
  "sect.reading.t2.title": { lv: "2. uzdevums", en: "Task 2", ru: "Задание 2" },
  "sect.reading.t2.body": {
    lv: "6 personas · 12 sludinājumi (A–L)",
    en: "6 people · 12 adverts (A–L)",
    ru: "6 человек · 12 объявлений (A–L)",
  },
  "sect.reading.t3.title": { lv: "3. uzdevums", en: "Task 3", ru: "Задание 3" },
  "sect.reading.t3.body": {
    lv: "1 teksts · 5 cloze gaps",
    en: "1 text · 5 cloze gaps",
    ru: "1 текст · 5 пропусков",
  },
  "sect.reading.tip": {
    lv: "Vispirms apskatiet apgalvojumus, tad meklējiet atbildes tekstā.",
    en: "Read the statements first, then look for the answers in the text.",
    ru: "Сначала прочитайте утверждения, потом ищите ответы в тексте.",
  },

  // Writing transition
  "sect.writing.heading": { lv: "Rakstītprasme", en: "Writing", ru: "Письмо" },
  "sect.writing.lead": {
    lv: "Šajā simulācijā rakstiet uz ekrāna — īstā pārbaudē uz papīra ar zilu vai melnu pildspalvu.",
    en: "In this simulator you type on screen — in the real exam you write on paper with a blue or black pen.",
    ru: "В симуляторе вы печатаете на экране — на реальном экзамене пишут на бумаге синей или чёрной ручкой.",
  },
  "sect.writing.t1.title": { lv: "1. uzdevums", en: "Task 1", ru: "Задание 1" },
  "sect.writing.t1.body": {
    lv: "4 foto · katrs ≥5 vārdu teikums",
    en: "4 photos · each needs a ≥5-word sentence",
    ru: "4 фото · к каждому предложение из ≥5 слов",
  },
  "sect.writing.t2.title": { lv: "2. uzdevums", en: "Task 2", ru: "Задание 2" },
  "sect.writing.t2.body": {
    lv: "5 vārdi pareizajā locījumā",
    en: "5 words in the correct grammatical form",
    ru: "5 слов в правильной форме",
  },
  "sect.writing.t3.title": { lv: "3. uzdevums", en: "Task 3", ru: "Задание 3" },
  "sect.writing.t3.body": {
    lv: "Sludinājums vai vēstule · ~35 vārdi",
    en: "Classified ad or short letter · ~35 words",
    ru: "Объявление или письмо · ~35 слов",
  },
  "sect.writing.tip": {
    lv: "Ievērojiet visus četrus plāna punktus — par katru izlaisto zaudē punktu.",
    en: "Cover all four plan points — you lose a point for each one you skip.",
    ru: "Учтите все четыре пункта плана — за пропущенный пункт снимают балл.",
  },

  // Speaking transition
  "sect.speaking.heading": { lv: "Runātprasme", en: "Speaking", ru: "Говорение" },
  "sect.speaking.lead": {
    lv: "Saruna ar eksaminētāju klātienē vai videokonferencē.",
    en: "A conversation with the examiner, in person or by video call.",
    ru: "Беседа с экзаменатором лично или по видеосвязи.",
  },
  "sect.speaking.t1.title": { lv: "1. uzdevums", en: "Task 1", ru: "Задание 1" },
  "sect.speaking.t1.body": {
    lv: "Intervija · 9–10 jautājumi",
    en: "Interview · 9–10 questions",
    ru: "Интервью · 9–10 вопросов",
  },
  "sect.speaking.t2.title": { lv: "2. uzdevums", en: "Task 2", ru: "Задание 2" },
  "sect.speaking.t2.body": {
    lv: "2 attēli · KAS · KO DARA · KUR",
    en: "2 images · WHO · DOING · WHERE",
    ru: "2 изображения · КТО · ЧТО ДЕЛАЕТ · ГДЕ",
  },
  "sect.speaking.t3.title": { lv: "3. uzdevums", en: "Task 3", ru: "Задание 3" },
  "sect.speaking.t3.body": {
    lv: "3 sludinājumi · uzdod jautājumu",
    en: "3 adverts · form a question for each",
    ru: "3 объявления · задайте вопрос",
  },
  "sect.speaking.tip": {
    lv: "Atbildiet pilnos teikumos. Ja nesapratāt — droši pārjautājiet.",
    en: "Answer in full sentences. Ask the examiner to repeat if needed.",
    ru: "Отвечайте полными предложениями. Если не поняли — попросите повторить.",
  },

  // ─── result screen ───────────────────────────────────────────
  "result.eyebrow": { lv: "VVPP A2 · 2024", en: "VVPP A2 · 2024", ru: "VVPP A2 · 2024" },
  "result.passed": {
    lv: ({ em }) => <>IR {em("nokārtots!")}</>,
    en: ({ em }) => <>You {em("passed!")}</>,
    ru: ({ em }) => <>{em("Сдано!")}</>,
  },
  "result.failed": {
    lv: ({ em }) => <>NAV {em("nokārtots")}</>,
    en: ({ em }) => <>Not {em("passed")}</>,
    ru: ({ em }) => <>{em("Не сдано")}</>,
  },
  "result.passed_lead": {
    lv: "Apsveicam! Katrā prasmē sasniegti vismaz 9 no 15 punktiem.",
    en: "Congratulations! You scored at least 9 of 15 points in every skill.",
    ru: "Поздравляем! Вы набрали не менее 9 из 15 баллов в каждом разделе.",
  },
  "result.failed_lead": {
    lv: "Lai pārbaudi nokārtotu, katrā prasmē jāsasniedz vismaz 9 no 15 punktiem.",
    en: "To pass, you need at least 9 of 15 points in every skill.",
    ru: "Для сдачи нужно набрать не менее 9 из 15 баллов в каждом разделе.",
  },
  "result.total": { lv: "Kopā", en: "Total", ru: "Всего" },
  "result.skill_pass": { lv: "nokārtots", en: "passed",  ru: "сдано" },
  "result.skill_fail": { lv: "vājš",      en: "below",   ru: "слабо" },
  "result.min": { lv: "min. 9", en: "min. 9", ru: "мин. 9" },
  "result.restart": { lv: "Sākt no jauna", en: "Start over", ru: "Начать заново" },
  "result.detailed": {
    lv: "Apskatīt detalizētu vērtējumu",
    en: "View detailed report",
    ru: "Подробный отчёт",
  },
  "result.export": { lv: "Eksportēt PDF", en: "Export PDF", ru: "Экспорт PDF" },
  "result.stamp.passed": { lv: "IR", en: "PASS", ru: "ДА" },
  "result.stamp.failed": { lv: "NAV", en: "FAIL", ru: "НЕТ" },
  "result.stamp.label": {
    lv: "NOKĀRTOTS", en: "VVPP A2", ru: "VVPP A2",
  },

  // ─── audio player ────────────────────────────────────────────
  "audio.title.task": {
    lv: ({ n }) => `${n}. uzdevums · Audioieraksts`,
    en: ({ n }) => `Task ${n} · Audio`,
    ru: ({ n }) => `Задание ${n} · Аудио`,
  },
  "audio.plays": { lv: "Atskaņojumi", en: "Plays", ru: "Прослушиваний" },

  // ─── per-task screen helper text (around exam content) ──────
  "screen.points": { lv: "Punkti", en: "Points", ru: "Баллы" },
  "screen.duration": { lv: "Ilgums", en: "Duration", ru: "Время" },

  // Listening 1
  "l1.lead": {
    lv: "Katrs paziņojums skanēs divas reizes. Pēc katra paziņojuma atzīmējiet pareizo atbildi.",
    en: "Each announcement plays twice. After each one, mark the correct answer.",
    ru: "Каждое объявление прозвучит дважды. После каждого отметьте правильный ответ.",
  },
  "l1.audio_label": {
    lv: "Seši paziņojumi (1.–6.)", en: "Six announcements (1–6)", ru: "Шесть объявлений (1–6)",
  },

  // Listening 2
  "l2.lead": {
    lv: "Saruna skanēs divas reizes. Atzīmējiet, vai apgalvojums ir pareizs (Jā) vai nepareizs (Nē).",
    en: "The dialogue plays twice. Mark whether each statement is true (Yes) or false (No).",
    ru: "Диалог прозвучит дважды. Отметьте, верно (Да) или неверно (Нет) каждое утверждение.",
  },
  "l2.audio_label": {
    lv: "Saruna veikalā “Modernās tehnoloģijas”",
    en: "Dialogue at the “Modernās tehnoloģijas” shop",
    ru: "Диалог в магазине «Modernās tehnoloģijas»",
  },
  "l2.context": { lv: "Konteksts", en: "Context", ru: "Контекст" },
  "l2.context_body": {
    lv: "Vīrietis zvana uz veikalu, jo viņa nesen pirktais dators pēkšņi nestrādā. Sarunā piedalās klients un veikala darbinieks.",
    en: "A man phones the shop because his recently bought computer suddenly stopped working. The dialogue is between the customer and a shop employee.",
    ru: "Мужчина звонит в магазин: недавно купленный компьютер вдруг перестал работать. В диалоге участвуют клиент и работник магазина.",
  },

  // Listening 3
  "l3.lead": {
    lv: "Ievelciet katrā teikumā atbilstošo skaitli vai vārdu no vārdu krātuves. Četras atbildes ir liekas.",
    en: "Drop the matching word or number into each sentence from the word bank. Four options are unused.",
    ru: "Перенесите в каждое предложение подходящее слово или число из набора. Четыре варианта лишние.",
  },
  "l3.audio_label": {
    lv: "Piecas īsas sarunas (1.–5.)", en: "Five short dialogues (1–5)", ru: "Пять коротких диалогов (1–5)",
  },
  "l3.bank_label": {
    lv: "Vārdu krātuve · klikšķiniet, lai ievilktu",
    en: "Word bank · click a word to drop it in",
    ru: "Набор слов · нажмите, чтобы вставить",
  },

  // Reading 1
  "r1.lead": {
    lv: "Četri īsi teksti. Par katru izvēlieties vienu apgalvojumu, kas tekstam atbilst.",
    en: "Four short texts. For each, choose the statement that matches.",
    ru: "Четыре коротких текста. К каждому выберите утверждение, соответствующее тексту.",
  },
  "r1.q": {
    lv: "Kurš apgalvojums atbilst tekstam?",
    en: "Which statement matches the text?",
    ru: "Какое утверждение соответствует тексту?",
  },

  // Reading 2
  "r2.lead": {
    lv: "Sešiem personu aprakstiem atrodiet vispiemērotāko sludinājumu no divpadsmit. Sešas reklāmas paliks neizmantotas.",
    en: "Match each of the six people to the best of twelve adverts. Six adverts will go unused.",
    ru: "Подберите подходящее объявление к каждому из шести описаний. Шесть объявлений останутся неиспользованными.",
  },
  "r2.choose": { lv: "Izvēle", en: "Choice", ru: "Выбор" },
  "r2.placeholder": { lv: "— izvēlieties —", en: "— choose —", ru: "— выберите —" },
  "r2.matched": {
    lv: ({ n }) => `${n}/6 saskaņoti`,
    en: ({ n }) => `${n}/6 matched`,
    ru: ({ n }) => `${n}/6 сопоставлено`,
  },
  "r2.ads_label": { lv: "Sludinājumi A–L", en: "Adverts A–L", ru: "Объявления A–L" },

  // Reading 3
  "r3.lead": {
    lv: "Teksts par Zariņu ģimenes vaļaspriekiem. Katrā tukšajā vietā ir trīs iespējamie varianti — izvēlieties vienu.",
    en: "A text about the Zariņš family hobbies. Each gap has three options — choose one.",
    ru: "Текст о хобби семьи Зариньш. В каждом пропуске три варианта — выберите один.",
  },

  // Writing 1
  "w1.lead": {
    lv: "Uzrakstiet par katru fotoattēlu vienu teikumu. Katrā teikumā — ne mazāk par 5 vārdiem.",
    en: "Write one sentence about each photo. Each sentence must have at least 5 words.",
    ru: "Напишите по одному предложению к каждой фотографии — не менее 5 слов каждое.",
  },
  "w1.example": { lv: "Paraugs", en: "Example", ru: "Пример" },
  "w1.example_text": {
    lv: "“Laura un Gusts brīvdienās labprāt apmeklē muzejus.”",
    en: "“Laura and Gusts enjoy visiting museums on weekends.”",
    ru: "«Лаура и Густ по выходным любят ходить в музеи».",
  },
  "w1.placeholder": {
    lv: "Uzrakstiet teikumu (≥ 5 vārdi)…",
    en: "Write a sentence (≥ 5 words)…",
    ru: "Напишите предложение (≥ 5 слов)…",
  },
  "w1.words": { lv: "Vārdi", en: "Words", ru: "Слов" },

  // Writing 3
  "w3.lead": {
    lv: "Pārbaudē jums izsniedz vienu variantu. Šajā simulācijā varat izvēlēties.",
    en: "In the real exam you get one variant. In this simulator you may choose.",
    ru: "На экзамене дают один вариант. В симуляторе можно выбрать.",
  },
  "w3.v1.label": {
    lv: "1. variants · Vēstule par ceļojumu",
    en: "Variant 1 · Letter about a trip",
    ru: "Вариант 1 · Письмо о поездке",
  },
  "w3.v2.label": {
    lv: "2. variants · Sludinājums par krēsliem",
    en: "Variant 2 · Advert selling chairs",
    ru: "Вариант 2 · Объявление о продаже стульев",
  },
  "w3.plan": { lv: "Plāna punkti", en: "Plan points", ru: "Пункты плана" },
  "w3.plan_hint": {
    lv: "Par katru izlaisto punktu zaudē vienu balli.",
    en: "You lose one point for each plan item you skip.",
    ru: "За каждый пропущенный пункт снимают балл.",
  },
  "w3.paper_head": { lv: "Atbildes lapa", en: "Answer sheet", ru: "Лист ответа" },
  "w3.placeholder_letter": {
    lv: "Sveiki, [vārds]!\nPagājušajā nedēļā es biju…",
    en: "Hi, [name]!\nLast week I was…",
    ru: "Привет, [имя]!\nНа прошлой неделе я был(а)…",
  },
  "w3.placeholder_ad": {
    lv: "Pārdod sešus krēslus…",
    en: "Selling six chairs…",
    ru: "Продаются шесть стульев…",
  },
  "w3.plan_count": {
    lv: ({ n }) => `${n}/4`,
    en: ({ n }) => `${n}/4`,
    ru: ({ n }) => `${n}/4`,
  },

  // Writing 3 plan body — letter
  "w3.v1.intro": {
    lv: "Iedomājieties, ka jūs bijāt ceļojumā. Uzrakstiet draugam vai draudzenei īsziņu, kurā:",
    en: "Imagine you've just been on a trip. Write a short message to a friend in which you:",
    ru: "Представьте, что вы вернулись из поездки. Напишите другу короткое сообщение, в котором:",
  },
  "w3.v1.p1": { lv: "pastāstiet, kad un kur jūs bijāt;",                en: "say when and where you were;",                       ru: "расскажете, когда и где вы были;" },
  "w3.v1.p2": { lv: "raksturojiet pilsētu, valsti utt.;",                en: "describe the city, country, etc.;",                  ru: "опишете город, страну и т. д.;" },
  "w3.v1.p3": { lv: "uzrakstiet, kas jums ceļojumā patika un kas nepatika;", en: "say what you liked and disliked about the trip;",  ru: "напишете, что понравилось и не понравилось в поездке;" },
  "w3.v1.p4": { lv: "iesakiet draugam apmeklēt šo pilsētu vai valsti.",  en: "recommend the city or country to your friend.",      ru: "посоветуете другу посетить этот город или страну." },

  // Writing 3 plan body — ad
  "w3.v2.intro": {
    lv: "Iedomājieties, ka gribat pārdot krēslus. Uzrakstiet sludinājumu, kurā:",
    en: "Imagine you want to sell some chairs. Write an advert in which you:",
    ru: "Представьте, что хотите продать стулья. Напишите объявление, в котором:",
  },
  "w3.v2.p1": { lv: "pastāstiet, ko pārdodat;",                       en: "state what you're selling;",                ru: "укажете, что продаёте;" },
  "w3.v2.p2": { lv: "raksturojiet (skaitu, krāsu, materiālus u. tml.);", en: "describe them (quantity, colour, materials, etc.);", ru: "опишете (количество, цвет, материал и т. п.);" },
  "w3.v2.p3": { lv: "informējiet par cenu;",                          en: "give the price;",                            ru: "укажете цену;" },
  "w3.v2.p4": { lv: "uzrakstiet, kā ar jums sazināties.",             en: "explain how to contact you.",                ru: "сообщите, как с вами связаться." },

  // Speaking 1
  "s1.lead": {
    lv: "Atbildiet pilnos teikumos. Eksaminētājs uzdod 9–10 jautājumus par dažādām tēmām. Ja kas nav skaidrs — droši pārjautājiet.",
    en: "Answer in full sentences. The examiner will ask 9–10 questions on various topics. If something isn't clear, feel free to ask them to repeat.",
    ru: "Отвечайте полными предложениями. Экзаменатор задаст 9–10 вопросов на разные темы. Если что-то непонятно — попросите повторить.",
  },
  "s1.topics": { lv: "Tēmas", en: "Topics", ru: "Темы" },
  "s1.examiner_says": {
    lv: "Eksaminētājs jautā", en: "The examiner asks", ru: "Экзаменатор спрашивает",
  },
  "s1.answer_hint": {
    lv: "Atbildiet pilnos teikumos. Stāstiet par sevi atklāti.",
    en: "Answer in full sentences. Speak about yourself openly.",
    ru: "Отвечайте полными предложениями. Рассказывайте о себе свободно.",
  },
  "s1.examiner_role": { lv: "Vērtētājs", en: "Examiner", ru: "Экзаменатор" },
  "s1.rec_start": { lv: "Sākt atbildi",    en: "Start answer",      ru: "Начать ответ"   },
  "s1.rec_stop":  { lv: "Apturēt ierakstu", en: "Stop recording",    ru: "Остановить запись" },
  "s1.rec_recording": {
    lv: "Ieraksta jūsu atbildi…", en: "Recording your answer…", ru: "Записываем ваш ответ…",
  },
  "s1.rec_saved": { lv: "Atbilde saglabāta", en: "Answer saved",  ru: "Ответ сохранён" },
  "s1.rec_ready": { lv: "Gatavs, kad jūs esat", en: "Ready when you are", ru: "Готовы, когда вы готовы" },

  // Speaking 2
  "s2.lead": {
    lv: "Pastāstiet par katru attēlu, atbildot uz jautājumiem KAS · KO DARA · KUR. Pēc tam atbildiet uz jautājumu par savu pieredzi.",
    en: "Describe each image by answering WHO · DOING WHAT · WHERE. Then answer the personal question.",
    ru: "Опишите каждое изображение, отвечая на вопросы КТО · ЧТО ДЕЛАЕТ · ГДЕ. Затем ответьте на личный вопрос.",
  },
  "s2.who":   { lv: "KAS?",     en: "WHO?",         ru: "КТО?" },
  "s2.doing": { lv: "KO DARA?", en: "DOING WHAT?",  ru: "ЧТО ДЕЛАЕТ?" },
  "s2.where": { lv: "KUR?",     en: "WHERE?",       ru: "ГДЕ?" },
  "s2.you":   { lv: "JUMS",     en: "YOU",          ru: "ВАМ" },
  "s2.q_who":   {
    lv: "Kas redzams attēlā? Kāds ir personu vecums un noskaņojums?",
    en: "Who's in the picture? What are their age and mood?",
    ru: "Кто на изображении? Каков их возраст и настроение?",
  },
  "s2.q_doing": {
    lv: "Ko cilvēki dara? Kā viņi svin? Vai kāds dzied, dejo, gatavo ēdienu?",
    en: "What are they doing? How are they celebrating? Is anyone singing, dancing, cooking?",
    ru: "Что они делают? Как празднуют? Кто-то поёт, танцует, готовит?",
  },
  "s2.q_where": {
    lv: "Kur tas notiek — mājās, dabā, sabiedriskā vietā? Kāds ir gadalaiks?",
    en: "Where is it happening — at home, outdoors, in public? What season is it?",
    ru: "Где это происходит — дома, на природе, в общественном месте? Какое время года?",
  },
  "s2.q_you": {
    lv: "Kurus svētkus jums patīk svinēt? Kāpēc tieši šos?",
    en: "Which holidays do you enjoy celebrating? Why those?",
    ru: "Какие праздники вы любите отмечать? Почему именно эти?",
  },
  "s2.notes": {
    lv: "Jūsu piezīmes (nav obligātas)",
    en: "Your notes (optional)",
    ru: "Ваши заметки (по желанию)",
  },
  "s2.notes_placeholder": {
    lv: "Atslēgas vārdi: ģimene, dāvanas, eglīte, ugunskurs…",
    en: "Keywords: family, gifts, Christmas tree, bonfire…",
    ru: "Ключевые слова: семья, подарки, ёлка, костёр…",
  },
  "s2.record_1min": {
    lv: "Ieraksts (1 min)", en: "Record (1 min)", ru: "Запись (1 мин)",
  },

  // Speaking 3
  "s3.lead": {
    lv: "Par katru sludinājumu formulējiet jautājumu pilnā teikumā, lai noskaidrotu trūkstošo informāciju.",
    en: "For each advert, form a full-sentence question to obtain the missing information.",
    ru: "К каждому объявлению составьте вопрос полным предложением, чтобы узнать недостающую информацию.",
  },
  "s3.ad_n": {
    lv: ({ n }) => `Sludinājums ${n}`,
    en: ({ n }) => `Advert ${n}`,
    ru: ({ n }) => `Объявление ${n}`,
  },
  "s3.your_question": { lv: "Jūsu jautājums", en: "Your question", ru: "Ваш вопрос" },
  "s3.q_placeholder": {
    lv: "Kurā datumā…?", en: "On what date…?", ru: "Какого числа…?",
  },
  "s3.target_date": { lv: "Uzziniet datumu", en: "Find out the date",  ru: "Узнайте дату"   },
  "s3.target_time": { lv: "Uzziniet laiku",  en: "Find out the time",  ru: "Узнайте время"  },
  "s3.target_floor":{ lv: "Uzziniet stāvu",  en: "Find out the floor", ru: "Узнайте этаж"   },
  "s3.record":      { lv: "Ieraksts", en: "Record", ru: "Запись" },

  // ─── language switcher itself ────────────────────────────────
  "lang.switcher_label": {
    lv: "Saskarne", en: "Interface", ru: "Интерфейс",
  },
};

// ── core hook / context ─────────────────────────────────────────
const I18nCtx = createContext({ lang: "lv", t: (k) => k, setLang: () => {} });

function I18nProvider({ lang, setLang, children }) {
  const t = (key, params) => {
    const entry = STRINGS[key];
    if (!entry) return key;
    const val = entry[lang] ?? entry.lv ?? key;
    if (typeof val === "function") return val(params || {});
    return val;
  };
  return <I18nCtx.Provider value={{ lang, t, setLang }}>{children}</I18nCtx.Provider>;
}

function useI18n() { return useContext(I18nCtx); }

// Tiny component for inlining a translation key (handy when JSX context can't easily call t())
function I18nT({ k, params }) {
  const { t } = useI18n();
  return <>{t(k, params)}</>;
}

// Tiny formatting helpers used by interpolated strings
const fmtBold = (txt) => <strong>{txt}</strong>;
const fmtEm   = (txt) => <em>{txt}</em>;

Object.assign(window, { LANGS, STRINGS, I18nCtx, I18nProvider, useI18n, I18nT, fmtBold, fmtEm });
