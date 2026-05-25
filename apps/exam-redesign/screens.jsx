// screens.jsx — every screen of the VVPP A2 learner runner.
// Content sourced from the official 2024 specimen booklet (VISC).

const { useState, useMemo } = React;

/* ═══════════════════════════════════════════════════════════════════
   SCREEN INDEX — used by app.jsx to drive navigation
   ═══════════════════════════════════════════════════════════════════ */
const SCREENS = [
  { id: "intro",         part: "intro" },

  { id: "listen-intro",  part: "listening" },
  { id: "listening-1",   part: "listening", task: "Paziņojumi",    points: 6 },
  { id: "listening-2",   part: "listening", task: "Saruna",        points: 4 },
  { id: "listening-3",   part: "listening", task: "Trūkstošie",    points: 5 },

  { id: "read-intro",    part: "reading"   },
  { id: "reading-1",     part: "reading",   task: "Apgalvojumi",   points: 4 },
  { id: "reading-2",     part: "reading",   task: "Sludinājumi",   points: 6 },
  { id: "reading-3",     part: "reading",   task: "Cloze",         points: 5 },

  { id: "write-intro",   part: "writing"   },
  { id: "writing-1",     part: "writing",   task: "Foto albums",   points: 4 },
  { id: "writing-3",     part: "writing",   task: "Brīva vēstule", points: 6 },

  { id: "speak-intro",   part: "speaking"  },
  { id: "speaking-1",    part: "speaking",  task: "Saruna",        points: 4 },
  { id: "speaking-2",    part: "speaking",  task: "Attēli",        points: 8 },
  { id: "speaking-3",    part: "speaking",  task: "Jautājumi",     points: 3 },

  { id: "submitted",     part: "submitted" },
];

/* ═══════════════════════════════════════════════════════════════════
   Reusable screen scaffolding
   ═══════════════════════════════════════════════════════════════════ */
function ScreenShell({ eyebrow, title, instructions, lead, children, points, time, side, footnote }) {
  const { t } = useI18n();
  return (
    <div className="screen">
      <header className="screen__head">
        <div className="screen__head-main">
          {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
          <h1 className="screen__title">{title}</h1>
          {lead ? <p className="screen__lead">{lead}</p> : null}
          {instructions ? (
            <ol className="screen__instructions">
              {instructions.map((i, n) => <li key={n}>{i}</li>)}
            </ol>
          ) : null}
        </div>
        {(points || time || side) ? (
          <aside className="screen__head-meta">
            {points ? <div className="meta-card"><span className="eyebrow">{t("screen.points")}</span><strong>{points}</strong></div> : null}
            {time ? <div className="meta-card"><span className="eyebrow">{t("screen.duration")}</span><strong>{time}</strong></div> : null}
            {side}
          </aside>
        ) : null}
      </header>
      <main className="screen__body">{children}</main>
      {footnote ? <footer className="screen__foot">{footnote}</footer> : null}
    </div>
  );
}

function QuestionCard({ index, total, prompt, children, points, status }) {
  return (
    <article className="qcard" data-status={status}>
      <header className="qcard__head">
        <div className="qcard__index">
          <span className="qcard__num">{index}</span>
          <span className="qcard__divider"/>
          <span className="qcard__total">{total}</span>
        </div>
        <div className="qcard__prompt">{prompt}</div>
        {points ? <div className="qcard__points"><span className="eyebrow">vērts</span><strong>{points}p</strong></div> : null}
      </header>
      <div className="qcard__body">{children}</div>
    </article>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   INTRO — welcome / pre-exam
   ═══════════════════════════════════════════════════════════════════ */
function IntroScreen({ onStart }) {
  const { t } = useI18n();
  return (
    <div className="intro">
      <div className="intro__brandstripe" aria-hidden="true">
        <span/><span/><span/>
      </div>

      <div className="intro__grid">
        <div className="intro__hero">
          <div className="eyebrow">{t("intro.eyebrow")}</div>
          <h1 className="intro__title">
            {t("intro.title_l1")} <br/>
            <em>{t("intro.title_l2")}</em>
          </h1>
          <p className="intro__lead">
            {t("intro.lead", { b: fmtBold })}
          </p>

          <div className="intro__cta">
            <button className="btn btn--lg" onClick={onStart}>
              {t("chrome.start_exam")} <Icon name="arrow" size={18}/>
            </button>
            <button className="btn btn--ghost btn--lg" onClick={onStart}>
              {t("chrome.practice_only")}
            </button>
          </div>
          <p className="intro__small">
            {t("intro.disclaimer")}
          </p>
        </div>

        <aside className="intro__rules card">
          <h3>{t("intro.rules.title")}</h3>
          <ul className="checklist">
            <li><Icon name="check" size={16}/> {t("intro.rules.r1")}</li>
            <li><Icon name="check" size={16}/> {t("intro.rules.r2")}</li>
            <li><Icon name="check" size={16}/> {t("intro.rules.r3")}</li>
            <li><Icon name="check" size={16}/> {t("intro.rules.r4")}</li>
          </ul>
          <div className="kbdhint">
            <span>{t("intro.kbdhint.nav")}</span>
            <span className="kbd">←</span><span className="kbd">→</span>
            <span>{t("intro.kbdhint.pause")}</span>
            <span className="kbd">␣</span>
          </div>
        </aside>
      </div>

      <section className="intro__sections">
        {PARTS.filter(p => p.id !== "intro").map((p, i) => (
          <div key={p.id} className="intro__section">
            <div className="intro__section-num">0{i + 1}</div>
            <div className="intro__section-icon"><Icon name={p.icon} size={22}/></div>
            <h3>{t(p.labelKey)}</h3>
            <div className="intro__section-meta">
              <span>{p.time} min</span>
              <span className="dot"/>
              <span>15 {String(t("sect.points")).toLowerCase()}</span>
              <span className="dot"/>
              <span>{t("intro.section.minimum")}</span>
            </div>
            <p className="intro__section-desc">
              {t(`intro.section.${p.id}.desc`)}
            </p>
          </div>
        ))}
      </section>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   SECTION INTRO — between-part transition
   ═══════════════════════════════════════════════════════════════════ */
function SectionIntro({ part, prevPart, onStart }) {
  const { t } = useI18n();
  const meta = PARTS.find(p => p.id === part);
  const prevMeta = prevPart ? PARTS.find(p => p.id === prevPart) : null;
  const detail = {
    listening: {
      heading: t("sect.listening.heading"),
      lead:    t("sect.listening.lead"),
      tasks: [
        [t("sect.listening.t1.title"), t("sect.listening.t1.body"), t("sect.points_short", { n: 6 })],
        [t("sect.listening.t2.title"), t("sect.listening.t2.body"), t("sect.points_short", { n: 4 })],
        [t("sect.listening.t3.title"), t("sect.listening.t3.body"), t("sect.points_short", { n: 5 })],
      ],
      tip: t("sect.listening.tip"),
    },
    reading: {
      heading: t("sect.reading.heading"),
      lead:    t("sect.reading.lead"),
      tasks: [
        [t("sect.reading.t1.title"), t("sect.reading.t1.body"), t("sect.points_short", { n: 4 })],
        [t("sect.reading.t2.title"), t("sect.reading.t2.body"), t("sect.points_short", { n: 6 })],
        [t("sect.reading.t3.title"), t("sect.reading.t3.body"), t("sect.points_short", { n: 5 })],
      ],
      tip: t("sect.reading.tip"),
    },
    writing: {
      heading: t("sect.writing.heading"),
      lead:    t("sect.writing.lead"),
      tasks: [
        [t("sect.writing.t1.title"), t("sect.writing.t1.body"), t("sect.points_short", { n: 4 })],
        [t("sect.writing.t2.title"), t("sect.writing.t2.body"), t("sect.points_short", { n: 5 })],
        [t("sect.writing.t3.title"), t("sect.writing.t3.body"), t("sect.points_short", { n: 6 })],
      ],
      tip: t("sect.writing.tip"),
    },
    speaking: {
      heading: t("sect.speaking.heading"),
      lead:    t("sect.speaking.lead"),
      tasks: [
        [t("sect.speaking.t1.title"), t("sect.speaking.t1.body"), t("sect.points_short", { n: 12 })],
        [t("sect.speaking.t2.title"), t("sect.speaking.t2.body"), t("sect.points_included")],
        [t("sect.speaking.t3.title"), t("sect.speaking.t3.body"), t("sect.points_short", { n: 3 })],
      ],
      tip: t("sect.speaking.tip"),
    },
  }[part];

  const prevName = prevMeta ? t(prevMeta.labelKey) : null;
  const partIdx = PARTS.findIndex(p => p.id === part);

  return (
    <div className="sectintro">
      <div className="sectintro__top">
        <div className="eyebrow">
          {prevName ? t("sect.prev_done", { name: prevName }) : t("sect.part_n")} {partIdx}/4
        </div>
        <div className="sectintro__icon"><Icon name={meta.icon} size={28}/></div>
      </div>
      <h1 className="sectintro__title">{detail.heading}</h1>
      <p className="sectintro__lead">{detail.lead}</p>

      <div className="sectintro__meta">
        <div className="metabig"><span className="eyebrow">{t("sect.duration")}</span><strong>{meta.time}<small>{t("sect.minutes_short")}</small></strong></div>
        <div className="metabig"><span className="eyebrow">{t("sect.points")}</span><strong>15</strong></div>
        <div className="metabig"><span className="eyebrow">{t("sect.pass")}</span><strong>≥ 9</strong></div>
      </div>

      <div className="sectintro__tasks">
        {detail.tasks.map((row, i) => (
          <div key={i} className="sectintro__task">
            <span className="sectintro__task-num">{i + 1}</span>
            <div>
              <strong>{row[0]}</strong>
              <p>{row[1]}</p>
            </div>
            <span className="tag tag--ghost">{row[2]}</span>
          </div>
        ))}
      </div>

      <div className="sectintro__tip">
        <Icon name="info" size={16}/>
        <span>{detail.tip}</span>
      </div>

      <div className="sectintro__cta">
        <button className="btn btn--lg" onClick={onStart}>
          {t("sect.start_cta", { part: detail.heading })} <Icon name="arrow" size={18}/>
        </button>
        <span className="sectintro__cta-hint">
          {t("sect.start_hint")}
        </span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   LISTENING 1 — 6 paziņojumi, multi-choice
   ═══════════════════════════════════════════════════════════════════ */
const L1_QUESTIONS = [
  { q: "Cikos ielidos lidmašīna?",
    opts: [["a","Pulksten 10.50."], ["b","Pulksten 10.20."], ["c","Pulksten 20.00."]] },
  { q: "Kur atrodas kafejnīca?",
    opts: [["a","Blakus pārtikas veikalam."], ["b","Otrajā stāvā blakus kāpnēm."], ["c","Jaunajā veikalā."]] },
  { q: "Kad var nopirkt biļetes ar atlaidi?",
    opts: [["a","Katru darbdienu."], ["b","Mēneša pēdējā dienā."], ["c","Mēneša pirmajā dienā."]] },
  { q: "Kāda būs biļetes cena vakarā?",
    opts: [["a","5 eiro."], ["b","2 eiro."], ["c","3 eiro."]] },
  { q: "Kas viesosies pasākumā?",
    opts: [["a","Sportists."], ["b","Rakstnieks."], ["c","Bibliotekārs."]] },
  { q: "Kāds laiks būs brīvdienās?",
    opts: [["a","Skaidrs un auksts."], ["b","Mākoņains un līs."], ["c","Silts un saulains."]] },
];

function Listening1({ state, set }) {
  const { t } = useI18n();
  const cardLayout = document.documentElement.dataset.cardlayout || "stacked";
  return (
    <ScreenShell
      eyebrow="Klausīšanās · 1. uzdevums"
      title="Klausieties paziņojumus!"
      lead={t("l1.lead")}
      points={6}
      time="≈ 8 min"
    >
      <AudioPlayer duration={138} label={t("l1.audio_label")} autoTitle={t("audio.title.task", { n: 1 })}/>

      <div className={`qgrid qgrid--${cardLayout}`}>
        {L1_QUESTIONS.map((q, i) => (
          <QuestionCard key={i} index={i + 1} total={6} prompt={q.q} points={1}
            status={state[i] ? "answered" : "open"}>
            <Choice
              value={state[i] || null}
              onChange={(v) => set(i, v)}
              options={q.opts.map(([v, l]) => ({ value: v, label: l, prefix: v.toUpperCase() }))}
              layout="stack"
            />
          </QuestionCard>
        ))}
      </div>
    </ScreenShell>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   LISTENING 2 — saruna, 4 apgalvojumi Jā/Nē
   ═══════════════════════════════════════════════════════════════════ */
const L2_STATEMENTS = [
  "Klients tikko nopirka jaunu datoru.",
  "Veikalā datorus gan pārdod, gan remontē.",
  "Klients pirka datoru, kad tam bija atlaide.",
  "Veikala darbinieks piedāvā remontēt datoru par maksu.",
];

function Listening2({ state, set }) {
  const { t } = useI18n();
  return (
    <ScreenShell
      eyebrow="Klausīšanās · 2. uzdevums"
      title="Klausieties sarunu!"
      lead={t("l2.lead")}
      points={4}
      time="≈ 6 min"
    >
      <div className="lt2__split">
        <div className="lt2__audio">
          <AudioPlayer duration={92} label={t("l2.audio_label")} autoTitle={t("audio.title.task", { n: 2 })}/>
          <div className="lt2__context card">
            <div className="eyebrow">{t("l2.context")}</div>
            <p>{t("l2.context_body")}</p>
          </div>
        </div>

        <div className="lt2__statements">
          {L2_STATEMENTS.map((s, i) => (
            <div key={i} className={`lt2__row card`} data-answered={!!state[i]}>
              <div className="lt2__row-num">{i + 1}</div>
              <div className="lt2__row-text">{s}</div>
              <YesNo value={state[i] || null} onChange={(v) => set(i, v)}/>
            </div>
          ))}
        </div>
      </div>
    </ScreenShell>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   LISTENING 3 — gap-fill from word bank
   ═══════════════════════════════════════════════════════════════════ */
const L3_BANK   = ["centrā", "zaļā", "tramvaju", "54", "autobusu", "bankas", "23.10", "veikala", "23.00"];
const L3_BLANKS = [
  ["Nakšņošana būs viesnīcā Tallinas ", " ."],
  ["Sieviete brauks uz bibliotēku ar ", "."],
  ["Raidījums būs pulksten ", "."],
  ["Vīrietis jautā par ", " darba laiku."],
  ["Sieviete grib uzmērīt cepuri ", " krāsā."],
];

function Listening3({ state, set }) {
  const { t } = useI18n();
  const used = new Set(state.filter(Boolean));
  const fillBlank = (idx, word) => {
    if (state[idx]) return; // clear first
    set(idx, word);
  };
  return (
    <ScreenShell
      eyebrow="Klausīšanās · 3. uzdevums"
      title="Klausieties piecas sarunas!"
      lead={t("l3.lead")}
      points={5}
      time="≈ 8 min"
    >
      <AudioPlayer duration={154} label={t("l3.audio_label")} autoTitle={t("audio.title.task", { n: 3 })}/>

      <div className="lt3__bank card">
        <div className="eyebrow">{t("l3.bank_label")}</div>
        <div className="lt3__chips">
          {L3_BANK.map(w => (
            <WordChip key={w} used={used.has(w)} onClick={() => {
              const empty = state.findIndex(v => !v);
              if (empty >= 0) fillBlank(empty, w);
            }}>{w}</WordChip>
          ))}
        </div>
      </div>

      <ol className="lt3__sentences">
        {L3_BLANKS.map((parts, i) => (
          <li key={i} className="lt3__sentence card" data-filled={!!state[i]}>
            <span className="lt3__num">{i + 1}.</span>
            <span className="lt3__text">
              {parts[0]}
              <Gap value={state[i]} onClear={() => set(i, null)} />
              {parts[1]}
            </span>
          </li>
        ))}
      </ol>
    </ScreenShell>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   READING 1 — passage + multiple choice
   ═══════════════════════════════════════════════════════════════════ */
const R1_PASSAGES = [
  {
    title: "Restorāns „Pie jūras“",
    body: [
      "Katru darbadienu no 12.00 līdz 15.00 — garšīgas pusdienas ar atlaidi, tikai 5.99 EUR!",
      "Šodien pusdienu ēdienkartē: salāti, lasis ar ceptiem kartupeļiem, šokolādes kūka „Sapnis” un sula vai kafija.",
      "Mūsu ēdienkartē atradīsiet ne vien latviešu, bet arī igauņu un lietuviešu tradicionālos ēdienus!",
      "Pirmdiena–piektdiena: 9.00–20.00. Sestdienās un svētdienās: slēgts.",
    ],
    opts: [
      ["a", "Restorāns piedāvā apmeklētājiem dažādu tautu ēdienus."],
      ["b", "Reklāmā nav informācijas par ēdienu komplekta cenu."],
      ["c", "Restorāns strādā katru dienu bez brīvdienām."],
    ],
  },
  {
    title: "Vēstule Jurim",
    body: [
      "Atnāc, lūdzu, piektdien, 20. februārī, uz manu dzimšanas dienas ballīti.",
      "Tā sāksies 18.00 pie manis mājās. Es uzaicināju arī savus draugus Ivaru un Aiju. Cepsim picas. Būs torte un šampanietis.",
      "Vakarā mēs plānojam aiziet uz nakts klubu padejot. Vai Tu arī nāksi? Ivars brauks ar mašīnu, un pēc kluba viņš visus aizvedīs uz mājām.",
      "Darba kolēģe Maija, Ceriņu ielā 3–50",
    ],
    opts: [
      ["a", "Maija ielūdz uz dzimšanas dienu savu darbabiedru."],
      ["b", "Juris var ņemt uz ballīti līdzi arī savus draugus."],
      ["c", "Maija jautā, vai Juris var aizvest ciemiņus pēc kluba uz mājām."],
    ],
  },
  {
    title: "Ēdienu vajag gatavot ar prieku",
    body: [
      "“Abi mani vecāki ir mākslinieki. Viņi vēlējās, lai pēc pamatskolas es mācos mākslas skolā. Es tur gribēju iestāties, bet netiku, jo nepratu labi zīmēt.",
      "Vasarā sāku strādāt viesnīcā par virtuves palīgu. Darbs virtuvē man patika, jo arī pavāra profesija ir interesanta, tādēļ es sāku mācīties pavāru skolā,” tā par savas profesijas izvēli stāsta Jānis Bērziņš.",
      "Tagad Jānis strādā restorānā. “Es gatavoju galvenokārt gaļas ēdienus un zupas. Es rūpējos, lai visi produkti ir svaigi.”",
    ],
    opts: [
      ["a", "Restorāna viesi vairāk pasūta ēdienus, kuriem ir neparasts izskats."],
      ["b", "Jānis mācījās par pavāru, jo viņam patika strādāt virtuvē."],
      ["c", "Pēc pamatskolas Jānis gāja zīmēšanas kursos."],
    ],
  },
  {
    title: "Sludinājums darbavietai",
    body: [
      "Apmācīsim jaunus darbiniekus mūsu firmas centrālajā birojā Rīgā. Apmācība ilgst divas nedēļas. Pieredze nav nepieciešama — visu iemācīs kolēģi.",
      "Pēc apmācībām strādās uzņēmuma kantorī Brīvības ielā. Darba laiks 9.00–17.00, brīvdienas sestdien un svētdien. Sūtiet CV uz darbs@firma.lv.",
    ],
    opts: [
      ["a", "Darbinieks strādās aptiekā."],
      ["b", "Darbiniekam vajag atnest dokumentus uz firmas biroju."],
      ["c", "Darbinieku apmācīs kolēģi."],
    ],
  },
];

function Reading1({ state, set }) {
  const { t } = useI18n();
  return (
    <ScreenShell
      eyebrow="Lasītprasme · 1. uzdevums"
      title="Lasiet tekstus un atzīmējiet pareizo apgalvojumu!"
      lead={t("r1.lead")}
      points={4}
      time="≈ 10 min"
    >
      <div className="r1__list">
        {R1_PASSAGES.map((p, i) => (
          <article key={i} className="r1__item">
            <div className="r1__passage card">
              <div className="r1__num">0{i + 1}</div>
              <h3 className="r1__title">{p.title}</h3>
              {p.body.map((para, n) => <p key={n} className="r1__para">{para}</p>)}
            </div>
            <div className="r1__question">
              <QuestionCard index={i + 1} total={4} prompt={t("r1.q")} points={1}
                status={state[i] ? "answered" : "open"}>
                <Choice
                  value={state[i] || null}
                  onChange={(v) => set(i, v)}
                  options={p.opts.map(([v, l]) => ({ value: v, label: l, prefix: v.toUpperCase() }))}
                />
              </QuestionCard>
            </div>
          </article>
        ))}
      </div>
    </ScreenShell>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   READING 2 — match persons to ads
   ═══════════════════════════════════════════════════════════════════ */
const R2_PEOPLE = [
  { id: 1, body: "Haralds ir no Latgales. Pēc vidusskolas viņš studēs medicīnu. Viņš meklē vietu galvaspilsētā, kur dzīvot studiju laikā." },
  { id: 2, body: "Anitas meitai ļoti patīk ārzemju dziedātāja Adriana. Viņa arī vēlas izskatīties kā dziedātāja un grib tādu matu griezumu kā Adrianai." },
  { id: 3, body: "Kaspara draudzenei Zanei drīz būs dzimšanas diena. Viņa jau divus gadus dzīvo Itālijā. Kaspars grib sūtīt viņai dāvanu — viņš nopirka Zanei skaistus auskarus." },
  { id: 4, body: "Ilzes dēls visu dienu ar draugiem ārā spēlēja bumbu. Kad viņš vakarā atnāca mājās, viņam bija augsta temperatūra un sākās klepus. Ilzei nav zāļu pret klepu." },
  { id: 5, body: "Edgaram salūza mašīna. Nestrādā ātrumkārba, un vajag regulēt bremzes. Viņš meklē meistaru, kas to var ātri salabot." },
  { id: 6, body: "Artūra māsai drīz būs dzimšanas diena. Viņa daudz lasa un krāj grāmatas ar autogrāfiem. Artūrs vēlas viņai šādu grāmatu uzdāvināt." },
];
const R2_ADS = [
  { id: "A", title: "Aptieka „Veseliba“",  body: "Plašs zāļu klāsts pret klepu un saaukstēšanos. Strādājam 24h. Pasakas iela 5, Rīga." },
  { id: "B", title: "Mēbeļu izstāde",      body: "Skandināvu dizaina krēsli un galdi. Studentu atlaides līdz 30%. Pieteikumi tikai darbdienās." },
  { id: "C", title: "Antikvariāts „Pirmizdevums“", body: "Grāmatas ar autoru autogrāfiem, retas mūzikas plates, vēstules. Rīga, Vecpilsētā." },
  { id: "D", title: "Studentu kopmītnes Rīgā", body: "Numuriņi diviem ar virtuvi un Wi-Fi. Tuvu Latvijas Universitātei un Medicīnas akadēmijai. No 120€/mēn." },
  { id: "E", title: "Auto serviss „Ātrums“",  body: "Bremžu regulēšana, ātrumkārbu remonts vienā dienā. Garantija. Brīvības gatve 187." },
  { id: "F", title: "Frizētava „Adriana“",   body: "Modernas frizūras, kā skatuves dīvām. Krāsošana un griešana. Pieraksts pa tālruni." },
  { id: "G", title: "Picērija „Romina“",      body: "Itāļu picas, pasta, tiramisu. Piegāde Rīgas centrā 30 min." },
  { id: "H", title: "Dāvanu veikals „Auseklis“", body: "Auskari, kakla rotas, suvenīri. Iesaiņojam dāvanas. Stacijas laukums 4." },
  { id: "I", title: "Skolas Adrianai",       body: "Mūzikas skola pieaugušajiem. Dziedāšana, klavieres. Lekcijas vakaros." },
  { id: "J", title: "Sūtījumi uz Eiropu",     body: "Ātrs pasta serviss uz Itāliju, Spāniju un Vāciju. Mazās paciņas no 6.50€." },
  { id: "K", title: "Bibliotēka „Sapnis“",   body: "Bezmaksas grāmatu apmaiņa un lasītava. Atvērts darbdienās 9–20." },
  { id: "L", title: "Veikals „Sporta nams“", body: "Sporta apavi, futbolbumbas, treniņtērpi. Atlaide visu janvāri." },
];

function Reading2({ state, set }) {
  const { t } = useI18n();
  const used = new Set(Object.values(state));
  return (
    <ScreenShell
      eyebrow="Lasītprasme · 2. uzdevums"
      title="Atrodiet sludinājumu (A–L) katrai personai!"
      lead={t("r2.lead")}
      points={6}
      time="≈ 12 min"
    >
      <div className="r2">
        <ol className="r2__people">
          {R2_PEOPLE.map(p => (
            <li key={p.id} className="r2__person card" data-answered={!!state[p.id]}>
              <div className="r2__person-head">
                <span className="r2__person-num">{p.id}</span>
                <strong>{p.body.split(".")[0]}.</strong>
              </div>
              <p className="r2__person-body">{p.body}</p>
              <div className="r2__person-pick">
                <span className="eyebrow">{t("r2.choose")}</span>
                <select
                  value={state[p.id] || ""}
                  onChange={(e) => set(p.id, e.target.value || null)}
                  aria-label={`Sludinājums personai ${p.id}`}
                >
                  <option value="">{t("r2.placeholder")}</option>
                  {R2_ADS.map(a => (
                    <option key={a.id} value={a.id}
                      disabled={used.has(a.id) && state[p.id] !== a.id}>
                      {a.id} · {a.title}
                    </option>
                  ))}
                </select>
              </div>
            </li>
          ))}
        </ol>

        <aside className="r2__ads">
          <div className="r2__ads-head">
            <div className="eyebrow">{t("r2.ads_label")}</div>
            <div className="r2__ads-counter">{t("r2.matched", { n: used.size })}</div>
          </div>
          <div className="r2__ads-grid">
            {R2_ADS.map(a => (
              <div key={a.id} className={`r2__ad`} data-used={used.has(a.id)}>
                <div className="r2__ad-letter">{a.id}</div>
                <h4>{a.title}</h4>
                <p>{a.body}</p>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </ScreenShell>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   READING 3 — cloze
   ═══════════════════════════════════════════════════════════════════ */
const R3_GAPS = [
  { before: "Gandrīz katram Zariņu ģimenē ir kāds hobijs. Juris brīvajā laikā aizraujas ",
    answer: "ar", choices: ["ar", "no", "uz"] },
  { before: "lasīšanu. Viņa draugi zina, ka Juri ",
    answer: "visvairāk", choices: ["visvairāk", "pavisam", "labāk"] },
  { before: "interesē detektīvromāni, tāpēc dzimšanas dienās dāvina viņam grāmatas. Jura dēlam Andrim ",
    answer: "patīk", choices: ["patīk", "garšo", "ir"] },
  { before: "aktīva atpūta. Viņš brauc velosipēdu un slēpo. Andra jaunākā māsa krāj konfekšu papīriņus. Ar to viņa ",
    answer: "nodarbojas", choices: ["spēlējas", "nodarbojas", "tirgojas"] },
  { before: "kopš piecu gadu vecuma. Tagad viņas ",
    answer: "kolekcijā", choices: ["albumā", "kolekcijā", "klasē"] },
];

function Reading3({ state, set }) {
  const { t } = useI18n();
  return (
    <ScreenShell
      eyebrow="Lasītprasme · 3. uzdevums"
      title="Lasiet tekstu un izvēlieties pareizo vārdu!"
      lead={t("r3.lead")}
      points={5}
      time="≈ 8 min"
    >
      <div className="r3 card">
        <div className="eyebrow">Atpūta</div>
        <p className="r3__body">
          {R3_GAPS.map((g, i) => (
            <React.Fragment key={i}>
              {g.before}
              <InlineSelect
                value={state[i]}
                options={g.choices}
                onChange={(v) => set(i, v)}
                label={`Tukšums ${i + 1}`}
              />
              {" "}
            </React.Fragment>
          ))}
          ir jau vairāk nekā simts dažādu konfekšu papīriņu. Sievas Ilzes vaļasprieks ir ceļošana.
        </p>
      </div>

      <div className="r3__progress">
        {R3_GAPS.map((_, i) => (
          <div key={i} className="r3__progress-dot" data-filled={!!state[i]}>{i + 1}</div>
        ))}
      </div>
    </ScreenShell>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   WRITING 1 — image-to-sentence (4 photos)
   ═══════════════════════════════════════════════════════════════════ */
const W1_PHOTOS = [
  { label: "1. attēls", hint: "ģimene · brīvdienas · futbols" },
  { label: "2. attēls", hint: "deja · skola · bērni" },
  { label: "3. attēls", hint: "mājdzīvnieks · suns" },
  { label: "4. attēls", hint: "filma · vakars · TV" },
];

function Writing1({ state, set }) {
  const { t } = useI18n();
  return (
    <ScreenShell
      eyebrow="Rakstītprasme · 1. uzdevums"
      title="Apskatiet foto albumu!"
      lead={t("w1.lead")}
      points={4}
      time="≈ 10 min"
    >
      <div className="w1__paraugs card">
        <span className="eyebrow">{t("w1.example")}</span>
        <p><em>{t("w1.example_text")}</em></p>
      </div>

      <div className="w1__grid">
        {W1_PHOTOS.map((p, i) => {
          const wc = (state[i] || "").trim().split(/\s+/).filter(Boolean).length;
          const ok = wc >= 5;
          return (
            <div key={i} className="w1__cell card">
              <ImagePlaceholder label={p.label} hint={p.hint} variant={i + 1}/>
              <div className="w1__writebox">
                <textarea
                  rows={3}
                  placeholder={t("w1.placeholder")}
                  value={state[i] || ""}
                  onChange={(e) => set(i, e.target.value)}
                />
                <div className="w1__counter" data-ok={ok}>
                  <span className="eyebrow">{t("w1.words")}</span>
                  <strong>{wc}/5+</strong>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </ScreenShell>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   WRITING 3 — long-form (letter OR ad)
   ═══════════════════════════════════════════════════════════════════ */
// W3 variant config is built inside the component so it can use t()

function Writing3({ state, set, variant, setVariant }) {
  const { t } = useI18n();
  const W3_VARIANTS = {
    letter: {
      label: t("w3.v1.label"),
      intro: t("w3.v1.intro"),
      points: [t("w3.v1.p1"), t("w3.v1.p2"), t("w3.v1.p3"), t("w3.v1.p4")],
    },
    ad: {
      label: t("w3.v2.label"),
      intro: t("w3.v2.intro"),
      points: [t("w3.v2.p1"), t("w3.v2.p2"), t("w3.v2.p3"), t("w3.v2.p4")],
    },
  };
  const v = W3_VARIANTS[variant];
  const text = state.text || "";
  const checks = state.checks || {};
  const wc = text.trim().split(/\s+/).filter(Boolean).length;
  const ok = wc >= 30;

  return (
    <ScreenShell
      eyebrow="Rakstītprasme · 3. uzdevums"
      title="Brīva teksta uzdevums"
      lead={t("w3.lead")}
      points={6}
      time="≈ 15 min"
    >
      <div className="w3__variants">
        {Object.entries(W3_VARIANTS).map(([key, val]) => {
          const parts = String(val.label).split(" · ");
          return (
            <button key={key} type="button" className="w3__variant"
              data-active={variant === key}
              onClick={() => setVariant(key)}>
              <div className="eyebrow">{parts[0]}</div>
              <strong>{parts[1] || parts[0]}</strong>
            </button>
          );
        })}
      </div>

      <div className="w3__layout">
        <aside className="w3__plan card">
          <div className="eyebrow">{t("w3.plan")}</div>
          <p className="w3__plan-intro">{v.intro}</p>
          <ol className="w3__plan-list">
            {v.points.map((pt, i) => (
              <li key={i}>
                <label>
                  <input type="checkbox"
                    checked={!!checks[i]}
                    onChange={(e) => set({ ...state, checks: { ...checks, [i]: e.target.checked } })}/>
                  <span>{pt}</span>
                </label>
              </li>
            ))}
          </ol>
          <div className="w3__plan-hint">
            <Icon name="info" size={14}/>
            <span>{t("w3.plan_hint")}</span>
          </div>
        </aside>

        <div className="w3__write">
          <div className="w3__paper card">
            <div className="w3__paper-head">
              <span className="eyebrow">{t("w3.paper_head")}</span>
              <span className="w3__paper-code">A2-2024-{(Math.random() * 9000 + 1000) | 0}</span>
            </div>
            <textarea
              className="w3__textarea"
              rows={16}
              placeholder={variant === "letter" ? t("w3.placeholder_letter") : t("w3.placeholder_ad")}
              value={text}
              onChange={(e) => set({ ...state, text: e.target.value })}
            />
            <div className="w3__paper-foot">
              <div className="w3__counter" data-ok={ok}>
                <span className="eyebrow">{t("w1.words")}</span>
                <strong>{wc}</strong>
                <span className="w3__counter-target">/ 35</span>
              </div>
              <div className="w3__counter">
                <span className="eyebrow">{t("w3.plan")}</span>
                <strong>{Object.values(checks).filter(Boolean).length}/4</strong>
              </div>
            </div>
          </div>
        </div>
      </div>
    </ScreenShell>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   SPEAKING 1 — interview
   ═══════════════════════════════════════════════════════════════════ */
const S1_TOPICS = [
  { topic: "Iepazīšanās", q: [
    "Kāds ir jūsu vārds un uzvārds?",
    "Kurā pilsētā jūs dzīvojat?",
    "Cik ilgi jūs jau dzīvojat šajā vietā?",
    "Kāda ir jūsu profesija vai nodarbošanās?",
    "Kurā vietā atrodas jūsu darbavieta vai mācību iestāde?",
  ]},
  { topic: "Iepirkšanās", q: [
    "Kur jūs pērkat pārtikas produktus?",
    "Ko jūs biežāk pērkat veikalā?",
    "Kur jums labāk patīk pirkt — veikalā vai tirgū? Kāpēc?",
  ]},
  { topic: "Atpūta, brīvais laiks", q: [
    "Ko jūs darāt vakaros pēc darba vai brīvdienās?",
    "Kā jūs parasti atpūšaties atvaļinājuma laikā?",
    "Kurš sporta veids jums patīk un kāpēc?",
  ]},
];

function Speaking1({ state, set }) {
  const { t } = useI18n();
  const [active, setActive] = useState(0);
  const [recordingIdx, setRecordingIdx] = useState(null);
  const flat = S1_TOPICS.flatMap(topic => topic.q);

  return (
    <ScreenShell
      eyebrow="Runātprasme · 1. uzdevums"
      title="Saruna ar eksaminētāju"
      lead={t("s1.lead")}
      points={12}
      time="≈ 6 min"
    >
      <div className="s1">
        <aside className="s1__topics card">
          <div className="eyebrow">{t("s1.topics")}</div>
          {S1_TOPICS.map((topic, i) => (
            <button key={i} type="button" className="s1__topic"
              data-active={active === i}
              onClick={() => setActive(i)}>
              <span className="s1__topic-num">{i + 1}</span>
              <span>{topic.topic}</span>
              <span className="s1__topic-count">{topic.q.length}</span>
            </button>
          ))}
        </aside>

        <div className="s1__stage">
          <div className="s1__examiner card">
            <div className="s1__bubble">
              <div className="eyebrow">{t("s1.examiner_says")}</div>
              <h2 className="s1__question">
                “{S1_TOPICS[active].q[0]}”
              </h2>
              <p className="s1__hint">{t("s1.answer_hint")}</p>
            </div>
            <div className="s1__avatar">
              <div className="s1__avatar-inner"><Icon name="user" size={28}/></div>
              <div className="s1__avatar-name">{t("s1.examiner_role")}</div>
            </div>
          </div>

          <div className="s1__recorder">
            <button className="s1__record"
              data-recording={recordingIdx !== null}
              onClick={() => {
                if (recordingIdx === null) { setRecordingIdx(active); set(active, "rec"); }
                else { setRecordingIdx(null); set(active, "done"); }
              }}>
              <span className="s1__record-ring"/>
              <Icon name="mic" size={28}/>
              <span className="s1__record-lbl">
                {recordingIdx !== null ? t("s1.rec_stop") : t("s1.rec_start")}
              </span>
            </button>
            <div className="s1__waveform" data-active={recordingIdx !== null}>
              {Array.from({ length: 32 }, (_, i) => (
                <span key={i} style={{ animationDelay: `${i * 60}ms` }}/>
              ))}
            </div>
            <div className="s1__status">
              {recordingIdx !== null
                ? <><span className="dot dot--rec"/> {t("s1.rec_recording")}</>
                : (state[active] === "done"
                  ? <><span className="dot dot--ok"/> {t("s1.rec_saved")}</>
                  : <span>{t("s1.rec_ready")}</span>)}
            </div>
          </div>

          <ol className="s1__list">
            {S1_TOPICS[active].q.map((q, i) => (
              <li key={i} className="s1__item" data-active={i === 0}>
                <span>{q}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </ScreenShell>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   SPEAKING 2 — images (KAS / KO DARA / KUR)
   ═══════════════════════════════════════════════════════════════════ */
function Speaking2({ state, set }) {
  const { t } = useI18n();
  return (
    <ScreenShell
      eyebrow="Runātprasme · 2. uzdevums"
      title="Aplūkojiet attēlus un atbildiet uz jautājumiem!"
      lead={t("s2.lead")}
      points={8}
      time="≈ 4 min"
    >
      <div className="s2">
        <div className="s2__images">
          <div className="s2__image"><ImagePlaceholder label="1. attēls" hint="Ziemassvētki · ģimene · pie galda" ratio="3/2" variant={5}/></div>
          <div className="s2__image"><ImagePlaceholder label="2. attēls" hint="Jāņi · ozolu vainagi · ugunskurs"  ratio="3/2" variant={4}/></div>
        </div>

        <div className="s2__prompts card">
          <div className="s2__qrow">
            <span className="tag tag--accent">{t("s2.who")}</span>
            <p>{t("s2.q_who")}</p>
          </div>
          <div className="s2__qrow">
            <span className="tag tag--accent">{t("s2.doing")}</span>
            <p>{t("s2.q_doing")}</p>
          </div>
          <div className="s2__qrow">
            <span className="tag tag--accent">{t("s2.where")}</span>
            <p>{t("s2.q_where")}</p>
          </div>
          <div className="divider"/>
          <div className="s2__qrow s2__qrow--you">
            <span className="tag tag--primary">{t("s2.you")}</span>
            <p><strong>{t("s2.q_you")}</strong></p>
          </div>
        </div>

        <div className="s2__notes card">
          <div className="eyebrow">{t("s2.notes")}</div>
          <textarea
            rows={5}
            placeholder={t("s2.notes_placeholder")}
            value={state.notes || ""}
            onChange={(e) => set({ ...state, notes: e.target.value })}
          />
          <button className="btn btn--ghost btn--sm">
            <Icon name="mic" size={14}/> {t("s2.record_1min")}
          </button>
        </div>
      </div>
    </ScreenShell>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   SPEAKING 3 — ask a question
   ═══════════════════════════════════════════════════════════════════ */
const S3_ADS = [
  { headline: "Valmieras Olimpiskajā centrā notiks basketbola spēle Latvija–Lietuva.",
    tail: "?", targetKey: "s3.target_date" },
  { headline: "Teātra izrāde “Laiks” 15. jūnijā sāksies pulksten",
    tail: "?", targetKey: "s3.target_time" },
  { headline: "Ģimenes ārstes Andras Kļaviņas kabinets atrodas",
    tail: "stāvā.", targetKey: "s3.target_floor" },
];

function Speaking3({ state, set }) {
  const { t } = useI18n();
  return (
    <ScreenShell
      eyebrow="Runātprasme · 3. uzdevums"
      title="Uzdodiet jautājumus!"
      lead={t("s3.lead")}
      points={3}
      time="≈ 3 min"
    >
      <div className="s3">
        {S3_ADS.map((ad, i) => (
          <article key={i} className="s3__card card" data-answered={!!(state[i] || "").trim()}>
            <div className="s3__num">0{i + 1}</div>
            <div className="s3__ad">
              <div className="eyebrow">{t("s3.ad_n", { n: i + 1 })}</div>
              <p className="s3__headline">
                {ad.headline}{" "}
                <span className="s3__missing">…&nbsp;?&nbsp;…</span>
                {ad.tail !== "?" ? ` ${ad.tail}` : ""}
              </p>
              <div className="s3__target tag tag--primary">
                <Icon name="info" size={12}/> {t(ad.targetKey)}
              </div>
            </div>
            <div className="s3__write">
              <label className="eyebrow">{t("s3.your_question")}</label>
              <textarea
                rows={2}
                placeholder={t("s3.q_placeholder")}
                value={state[i] || ""}
                onChange={(e) => set(i, e.target.value)}
              />
              <button className="btn btn--ghost btn--sm">
                <Icon name="mic" size={14}/> {t("s3.record")}
              </button>
            </div>
          </article>
        ))}
      </div>
    </ScreenShell>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   SUBMITTED — results / scoring
   ═══════════════════════════════════════════════════════════════════ */
function Submitted({ answers, onRestart }) {
  const { t } = useI18n();
  // mock scoring — count answered cells, scale to 15 points/section
  const score = useMemo(() => {
    const a = answers || {};
    const cnt = (obj, n) => {
      if (!obj) return 0;
      const vals = Array.isArray(obj) ? obj : Object.values(obj);
      return Math.min(n, vals.filter(v => v && v !== "rec").length);
    };
    const listening = cnt(a["listening-1"], 6) + cnt(a["listening-2"], 4) + cnt(a["listening-3"], 5);
    const reading   = cnt(a["reading-1"], 4) + cnt(a["reading-2"], 6) + cnt(a["reading-3"], 5);
    const w1c       = cnt(a["writing-1"], 4);
    const w3text    = (a["writing-3"]?.text || "").trim().split(/\s+/).filter(Boolean).length;
    const writing   = w1c + Math.min(6, Math.round(w3text / 6)) + (5 * 0.8 | 0);
    const speaking  = cnt(a["speaking-1"], 12) + cnt(a["speaking-3"], 3);
    return { listening, reading, writing, speaking };
  }, [answers]);

  const total = score.listening + score.reading + score.writing + score.speaking;
  const passed = score.listening >= 9 && score.reading >= 9 && score.writing >= 9 && score.speaking >= 9;
  const pct = Math.round((total / 60) * 100);

  return (
    <div className="result">
      <div className="result__top">
        <div className="eyebrow">{t("result.eyebrow")}</div>
        <h1 className="result__title">
          {passed ? t("result.passed", { em: fmtEm }) : t("result.failed", { em: fmtEm })}
        </h1>
        <p className="result__lead">
          {passed ? t("result.passed_lead") : t("result.failed_lead")}
        </p>
      </div>

      <div className="result__stamp" data-passed={passed}>
        <svg viewBox="0 0 200 200" width="180" height="180">
          <circle cx="100" cy="100" r="92" fill="none" stroke="currentColor" strokeWidth="3"/>
          <circle cx="100" cy="100" r="78" fill="none" stroke="currentColor" strokeWidth="1"/>
          <text x="100" y="92" textAnchor="middle" fontFamily="serif" fontSize="22" fontWeight="700" fill="currentColor">
            {passed ? t("result.stamp.passed") : t("result.stamp.failed")}
          </text>
          <text x="100" y="118" textAnchor="middle" fontFamily="serif" fontSize="18" fontWeight="600" fill="currentColor">
            {t("result.stamp.label")}
          </text>
          <text x="100" y="140" textAnchor="middle" fontFamily="monospace" fontSize="9" fill="currentColor" opacity=".7">
            VVPP · A2 · {pct}%
          </text>
        </svg>
      </div>

      <div className="result__totals">
        <div className="result__total">
          <span className="eyebrow">{t("result.total")}</span>
          <strong>{total}<small>/60</small></strong>
          <span className="result__total-pct">{pct}%</span>
        </div>
      </div>

      <div className="result__skills">
        {[
          ["listening", "part.listening", "headphones"],
          ["reading",   "part.reading",   "book"],
          ["writing",   "part.writing",   "pen"],
          ["speaking",  "part.speaking",  "mic"],
        ].map(([key, labelKey, icon]) => {
          const val = score[key];
          const passSkill = val >= 9;
          return (
            <div key={key} className="result__skill" data-pass={passSkill}>
              <div className="result__skill-head">
                <Icon name={icon} size={18}/>
                <strong>{t(labelKey)}</strong>
                <span className={`tag ${passSkill ? "tag--accent" : "tag--ghost"}`}>
                  {passSkill ? t("result.skill_pass") : t("result.skill_fail")}
                </span>
              </div>
              <div className="result__skill-bar">
                <div className="result__skill-fill" style={{ width: `${(val / 15) * 100}%` }} data-pass={passSkill}/>
                <div className="result__skill-min" style={{ left: `${(9 / 15) * 100}%` }} title={t("result.min")}/>
              </div>
              <div className="result__skill-meta">
                <span><strong>{val}</strong>/15</span>
                <span className="muted">{t("result.min")}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="result__cta">
        <button className="btn btn--lg" onClick={onRestart}>
          {t("result.restart")}
        </button>
        <button className="btn btn--ghost btn--lg">
          {t("result.detailed")}
        </button>
        <button className="btn btn--quiet btn--lg">
          {t("result.export")}
        </button>
      </div>
    </div>
  );
}

Object.assign(window, {
  SCREENS, ScreenShell, QuestionCard,
  IntroScreen, SectionIntro,
  Listening1, Listening2, Listening3,
  Reading1, Reading2, Reading3,
  Writing1, Writing3,
  Speaking1, Speaking2, Speaking3,
  Submitted,
});
