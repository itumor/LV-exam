// chrome.jsx — top bar, exam progress, side rail, timer.

const { useState, useEffect, useRef } = React;

/* ── Part labels (the 4 official VVPP A2 sections) ───────────────── */
const PARTS = [
  { id: "intro",     icon: "info",       labelKey: null,                shortKey: null,                  time: 0  },
  { id: "listening", icon: "headphones", labelKey: "part.listening",    shortKey: "part.listening.short", time: 25 },
  { id: "reading",   icon: "book",       labelKey: "part.reading",      shortKey: "part.reading.short",   time: 30 },
  { id: "writing",   icon: "pen",        labelKey: "part.writing",      shortKey: "part.writing.short",   time: 35 },
  { id: "speaking",  icon: "mic",        labelKey: "part.speaking",     shortKey: "part.speaking.short",  time: 12 },
];

// (label/short kept as fallbacks for non-i18n consumers)
PARTS[1].label = "Klausīšanās"; PARTS[1].short = "Klausīšanās";
PARTS[2].label = "Lasītprasme"; PARTS[2].short = "Lasīšana";
PARTS[3].label = "Rakstītprasme"; PARTS[3].short = "Rakstīšana";
PARTS[4].label = "Runātprasme"; PARTS[4].short = "Runāšana";

function partOfScreen(id) {
  if (id.startsWith("listening") || id === "listen-intro") return "listening";
  if (id.startsWith("reading")   || id === "read-intro")   return "reading";
  if (id.startsWith("writing")   || id === "write-intro")  return "writing";
  if (id.startsWith("speaking")  || id === "speak-intro")  return "speaking";
  if (id === "submitted")        return "speaking";
  return "intro";
}

/* ── Top app bar ─────────────────────────────────────────────────── */
function AppBar({ activePart, timerSecs, totalSecs, paused, onPause, onJump, onToggleTweaks, mode, onToggleMode, lang, onLang }) {
  const pct = totalSecs ? Math.max(0, Math.min(100, (timerSecs / totalSecs) * 100)) : 100;
  const danger = pct < 12;
  const timerStyle = document.documentElement.dataset.timer || "bar";
  const { t } = useI18n();

  return (
    <header className="appbar" data-danger={danger}>
      <div className="appbar__inner">
        <a className="brand" href="#" onClick={(e) => { e.preventDefault(); onJump("intro"); }}>
          <span className="brand__mark" aria-hidden="true">A2</span>
          <span className="brand__text">
            <span className="brand__title">VVPP</span>
            <span className="brand__sub">Latviešu&nbsp;valodas&nbsp;prasme</span>
          </span>
        </a>

        <nav className="appbar__nav" aria-label="Eksāmena daļas">
          {PARTS.filter(p => p.id !== "intro").map((p, i) => {
            const active = p.id === activePart;
            const done = PARTS.findIndex(x => x.id === activePart) > PARTS.findIndex(x => x.id === p.id);
            return (
              <button key={p.id}
                type="button"
                className="appbar__navitem"
                data-active={active}
                data-done={done}
                onClick={() => onJump(`${p.id}-intro`)}
              >
                <span className="appbar__navnum">{i + 1}</span>
                <span className="appbar__navlbl">{t(p.shortKey)}</span>
                <span className="appbar__navmeta">{p.time} min · 15p</span>
              </button>
            );
          })}
        </nav>

        <div className="appbar__right">
          {timerStyle === "ring" ? (
            <TimerRing secs={timerSecs} total={totalSecs} paused={paused} onPause={onPause}/>
          ) : timerStyle === "pill" ? (
            <TimerPill secs={timerSecs} total={totalSecs} paused={paused} onPause={onPause}/>
          ) : (
            <TimerBar secs={timerSecs} total={totalSecs} paused={paused} onPause={onPause}/>
          )}
          <LangSwitcher lang={lang} onLang={onLang} />
          <button className="iconbtn" type="button" onClick={onToggleMode} aria-label="Light / dark">
            <Icon name={mode === "dark" ? "sun" : "moon"} size={16}/>
          </button>
          <button className="iconbtn" type="button" onClick={onToggleTweaks} aria-label="Tweaks">
            <Icon name="cog" size={16}/>
          </button>
          <div className="avatar" aria-hidden="true">
            <Icon name="user" size={16}/>
          </div>
        </div>
      </div>
    </header>
  );
}

/* ── Language switcher (3-way segmented) ─────────────────────────── */
function LangSwitcher({ lang, onLang }) {
  return (
    <div className="langswitch" role="radiogroup" aria-label="Interface language">
      {LANGS.map(l => (
        <button
          key={l.id}
          type="button"
          role="radio"
          aria-checked={lang === l.id}
          data-active={lang === l.id}
          className="langswitch__btn"
          onClick={() => onLang(l.id)}
          title={l.name}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}

/* ── Timer variants ──────────────────────────────────────────────── */
function fmt(s) {
  const m = Math.floor(s / 60);
  const ss = String(Math.floor(s % 60)).padStart(2, "0");
  return `${String(m).padStart(2, "0")}:${ss}`;
}

function TimerBar({ secs, total, paused, onPause }) {
  const pct = total ? Math.max(0, Math.min(100, (secs / total) * 100)) : 100;
  const { t } = useI18n();
  return (
    <button className="timer timer--bar" type="button" onClick={onPause} data-paused={paused}>
      <div className="timer__face">
        <span className="eyebrow">{t("chrome.time_remaining")}</span>
        <span className="timer__digits">{fmt(secs)}</span>
      </div>
      <div className="timer__track" aria-hidden="true">
        <div className="timer__fill" style={{ width: `${pct}%` }} />
      </div>
    </button>
  );
}

function TimerRing({ secs, total, paused, onPause }) {
  const pct = total ? Math.max(0, Math.min(100, (secs / total) * 100)) : 100;
  const c = 2 * Math.PI * 18;
  return (
    <button className="timer timer--ring" type="button" onClick={onPause} data-paused={paused}>
      <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden="true">
        <circle cx="22" cy="22" r="18" fill="none" stroke="var(--line)" strokeWidth="3"/>
        <circle cx="22" cy="22" r="18" fill="none" stroke="var(--primary)" strokeWidth="3"
                strokeDasharray={`${(pct / 100) * c} ${c}`} strokeLinecap="round"
                transform="rotate(-90 22 22)"/>
      </svg>
      <span className="timer__digits">{fmt(secs)}</span>
    </button>
  );
}

function TimerPill({ secs, total, paused, onPause }) {
  return (
    <button className="timer timer--pill" type="button" onClick={onPause} data-paused={paused}>
      <Icon name="clock" size={14}/>
      <span className="timer__digits">{fmt(secs)}</span>
    </button>
  );
}

/* ── Sub-bar: task pagination within current part ────────────────── */
function TaskBar({ activeScreen, onJump, screens }) {
  const { t } = useI18n();
  const part = partOfScreen(activeScreen);
  const tasks = screens.filter(s => s.part === part && s.task);
  if (!tasks.length) return null;
  const i = tasks.findIndex(t => t.id === activeScreen);
  const partMeta = PARTS.find(p => p.id === part);

  return (
    <div className="taskbar">
      <div className="taskbar__inner">
        <div className="taskbar__title">
          <Icon name={partMeta?.icon || "info"} size={16}/>
          <strong>{partMeta?.labelKey ? t(partMeta.labelKey) : ""}</strong>
        </div>
        <div className="taskbar__steps">
          {tasks.map((task, idx) => (
            <button key={task.id}
              className="taskbar__step"
              type="button"
              data-active={idx === i}
              data-done={idx < i}
              onClick={() => onJump(task.id)}
            >
              <span className="taskbar__num">{idx + 1}</span>
              <span className="taskbar__lbl">{task.task}</span>
              <span className="taskbar__pts">{task.points}p</span>
            </button>
          ))}
        </div>
        <div className="taskbar__legend"><span className="kbd">←</span> <span className="kbd">→</span></div>
      </div>
    </div>
  );
}

/* ── Footer nav (Prev / Next) ────────────────────────────────────── */
function FooterNav({ canPrev, canNext, onPrev, onNext, nextLabel, prevLabel, hint, primary = false, lastInPart, lastOverall }) {
  const { t } = useI18n();
  return (
    <footer className="footnav">
      <div className="footnav__inner">
        <button type="button" className="btn btn--ghost" disabled={!canPrev} onClick={onPrev}>
          <Icon name="arrow-l" size={16}/> {prevLabel ?? t("chrome.back")}
        </button>
        <div className="footnav__hint">{hint}</div>
        <button
          type="button"
          className={`btn ${primary ? "" : "btn--ghost"}`}
          disabled={!canNext}
          onClick={onNext}
        >
          {lastOverall ? t("chrome.finish_exam") : lastInPart ? t("chrome.end_section") : (nextLabel ?? t("chrome.next"))}
          <Icon name="arrow" size={16}/>
        </button>
      </div>
    </footer>
  );
}

Object.assign(window, { LangSwitcher });

Object.assign(window, { PARTS, partOfScreen, AppBar, TimerBar, TimerRing, TimerPill, TaskBar, FooterNav });
