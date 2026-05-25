// controls.jsx — shared UI primitives for the exam runner.
// All elements respect the active theme via CSS variables.

const { useState, useEffect, useRef, useMemo } = React;

/* ── icon set (inline SVG, currentColor) ─────────────────────────── */
function Icon({ name, size = 18, stroke = 1.6, ...rest }) {
  const p = {
    width: size, height: size, viewBox: "0 0 24 24",
    fill: "none", stroke: "currentColor", strokeWidth: stroke,
    strokeLinecap: "round", strokeLinejoin: "round", ...rest,
  };
  switch (name) {
    case "play":   return <svg {...p}><path d="M7 5l12 7-12 7V5z" fill="currentColor" stroke="none"/></svg>;
    case "pause":  return <svg {...p}><rect x="6" y="5" width="4" height="14" fill="currentColor" stroke="none"/><rect x="14" y="5" width="4" height="14" fill="currentColor" stroke="none"/></svg>;
    case "replay": return <svg {...p}><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>;
    case "headphones": return <svg {...p}><path d="M4 16v-4a8 8 0 0 1 16 0v4"/><rect x="3" y="14" width="5" height="7" rx="1.5"/><rect x="16" y="14" width="5" height="7" rx="1.5"/></svg>;
    case "book":   return <svg {...p}><path d="M4 4h7a3 3 0 0 1 3 3v13"/><path d="M20 4h-7a3 3 0 0 0-3 3v13"/><path d="M4 4v15h7"/><path d="M20 4v15h-7"/></svg>;
    case "pen":    return <svg {...p}><path d="M12 19l-7 2 2-7L17 4l5 5L12 19z"/><path d="M15 6l5 5"/></svg>;
    case "mic":    return <svg {...p}><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/><path d="M8 21h8"/></svg>;
    case "arrow":  return <svg {...p}><path d="M5 12h14"/><path d="M13 6l6 6-6 6"/></svg>;
    case "arrow-l": return <svg {...p}><path d="M19 12H5"/><path d="M11 6l-6 6 6 6"/></svg>;
    case "check":  return <svg {...p}><path d="M5 12l5 5L20 7"/></svg>;
    case "x":      return <svg {...p}><path d="M6 6l12 12M18 6L6 18"/></svg>;
    case "clock":  return <svg {...p}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>;
    case "flag":   return <svg {...p}><path d="M5 21V4"/><path d="M5 4h12l-3 4 3 4H5"/></svg>;
    case "lock":   return <svg {...p}><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>;
    case "info":   return <svg {...p}><circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><circle cx="12" cy="8" r=".7" fill="currentColor"/></svg>;
    case "cog":    return <svg {...p}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 0 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 0 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 0 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 0 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9c.3.6.9 1 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>;
    case "moon":   return <svg {...p}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>;
    case "sun":    return <svg {...p}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>;
    case "user":   return <svg {...p}><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>;
    default: return null;
  }
}

/* ── Choice (radio) and YesNo (binary) primitives ────────────────── */
function Choice({ value, onChange, options, name, layout = "stack" }) {
  // options: [{value, label, prefix?}, ...]
  return (
    <div className={`choice choice--${layout}`} role="radiogroup">
      {options.map((opt) => {
        const selected = value === opt.value;
        return (
          <button
            type="button"
            key={opt.value}
            role="radio"
            aria-checked={selected}
            data-selected={selected}
            className="opt"
            onClick={() => onChange(opt.value)}
          >
            <span className="opt__dot" />
            <span className="opt__label">
              {opt.prefix ? <span className="opt__key">{opt.prefix}</span> : null}
              {opt.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function YesNo({ value, onChange }) {
  return (
    <div className="yesno">
      <button
        type="button"
        data-selected={value === "ja"}
        className="yesno__btn yesno__btn--yes"
        onClick={() => onChange(value === "ja" ? null : "ja")}
      >
        <span className="yesno__icon"><Icon name="check" size={20}/></span>
        <span>Jā</span>
      </button>
      <button
        type="button"
        data-selected={value === "ne"}
        className="yesno__btn yesno__btn--no"
        onClick={() => onChange(value === "ne" ? null : "ne")}
      >
        <span className="yesno__icon"><Icon name="x" size={20}/></span>
        <span>Nē</span>
      </button>
    </div>
  );
}

/* ── Audio player (simulated playback with progress bar) ─────────── */
function AudioPlayer({ duration = 42, label, plays = 0, maxPlays = 2, autoTitle = "Audioieraksts" }) {
  const { t } = useI18n();
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const [played, setPlayed] = useState(plays);
  const raf = useRef(0);
  const last = useRef(0);

  useEffect(() => {
    if (!playing) return;
    last.current = performance.now();
    const tick = (now) => {
      const dt = (now - last.current) / 1000;
      last.current = now;
      setPos(prev => {
        const nx = prev + dt;
        if (nx >= duration) { setPlaying(false); setPlayed(p => Math.min(maxPlays, p + 1)); return duration; }
        return nx;
      });
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [playing, duration, maxPlays]);

  const reset = () => { setPos(0); setPlaying(false); };
  const mm = (s) => `${String(Math.floor(s / 60)).padStart(1, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const pct = (pos / duration) * 100;
  const done = pos >= duration;
  const playsLeft = Math.max(0, maxPlays - played - (playing ? 1 : 0));

  return (
    <div className="audio">
      <div className="audio__head">
        <div className="audio__iconcell"><Icon name="headphones" size={22}/></div>
        <div className="audio__meta">
          <div className="audio__title">{autoTitle}</div>
          <div className="audio__sub">{label}</div>
        </div>
        <div className="audio__plays">
          <span className="eyebrow">{t("audio.plays")}</span>
          <strong>{maxPlays - playsLeft}/{maxPlays}</strong>
        </div>
      </div>
      <div className="audio__transport">
        <button
          type="button"
          className="audio__play"
          onClick={() => {
            if (done) { reset(); setTimeout(() => setPlaying(true), 50); return; }
            setPlaying(p => !p);
          }}
          aria-label={playing ? "Apturēt" : "Atskaņot"}
        >
          <Icon name={playing ? "pause" : (done ? "replay" : "play")} size={22}/>
        </button>
        <div className="audio__bar" aria-hidden="true">
          <div className="audio__bar-fill" style={{ width: `${pct}%` }} />
          <div className="audio__bar-wave">
            {Array.from({ length: 56 }, (_, i) => (
              <span key={i} style={{ height: `${20 + 70 * Math.abs(Math.sin(i * 0.42 + i * i * 0.03))}%`,
                opacity: (i / 56) * 100 < pct ? 1 : 0.32 }} />
            ))}
          </div>
        </div>
        <div className="audio__time">
          <span>{mm(pos)}</span>
          <span className="audio__time-sep">/</span>
          <span>{mm(duration)}</span>
        </div>
      </div>
    </div>
  );
}

/* ── Word chip (for drag/gap-fill bank) ──────────────────────────── */
function WordChip({ children, used, ...rest }) {
  return (
    <button type="button" className="chip" data-used={used} {...rest}>
      {children}
    </button>
  );
}

/* ── Gap (inline blank in a sentence) ────────────────────────────── */
function Gap({ value, onClear, placeholder = "_______" }) {
  return (
    <span className="gap" data-filled={!!value} onClick={value ? onClear : undefined} role="button" tabIndex={0}>
      {value || placeholder}
    </span>
  );
}

/* ── Select-in-line (cloze with dropdown) ────────────────────────── */
function InlineSelect({ value, options, onChange, label }) {
  return (
    <span className="isel">
      <select aria-label={label} value={value || ""} onChange={(e) => onChange(e.target.value)}>
        <option value="" disabled>—</option>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </span>
  );
}

/* ── Progress timer (used in chrome) ─────────────────────────────── */
function useCountdown(totalSeconds, running) {
  const [s, setS] = useState(totalSeconds);
  useEffect(() => setS(totalSeconds), [totalSeconds]);
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setS(v => Math.max(0, v - 1)), 1000);
    return () => clearInterval(id);
  }, [running]);
  return s;
}

/* ── Image placeholder card ──────────────────────────────────────── */
function ImagePlaceholder({ label, hint, ratio = "4/3", variant = 1 }) {
  // generate a stylised "photo" using SVG so we don't rely on external images
  const palettes = [
    ["#d8c69e", "#9a7c4d", "#3f3320"],
    ["#9bb8c9", "#4a6b80", "#1d2e3d"],
    ["#cba896", "#8a5a44", "#3a241a"],
    ["#a6bca0", "#5d7d59", "#243a2a"],
    ["#dac49a", "#a07842", "#3a2614"],
    ["#b6b1d8", "#675f9c", "#241e44"],
  ];
  const p = palettes[(variant - 1) % palettes.length];
  return (
    <div className="imgph" style={{ aspectRatio: ratio }}>
      <svg viewBox="0 0 200 150" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <defs>
          <linearGradient id={`sky-${variant}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={p[0]}/><stop offset="100%" stopColor={p[1]}/>
          </linearGradient>
        </defs>
        <rect width="200" height="150" fill={`url(#sky-${variant})`}/>
        <ellipse cx={40 + variant * 17} cy="40" rx="14" ry="14" fill="#fff" opacity=".7"/>
        <path d={`M0 ${90 + variant * 4} Q${50 + variant * 5} ${70 + variant * 3} 100 ${88 + variant * 2} T200 ${85 + variant * 3} V150 H0Z`} fill={p[2]}/>
        <path d={`M0 ${110 + variant * 2} Q60 ${100 + variant * 2} 120 ${108 + variant * 2} T200 ${112} V150 H0Z`} fill={p[1]} opacity=".7"/>
      </svg>
      <div className="imgph__label">
        <div className="eyebrow">{label}</div>
        {hint ? <div className="imgph__hint">{hint}</div> : null}
      </div>
    </div>
  );
}

Object.assign(window, {
  Icon, Choice, YesNo, AudioPlayer, WordChip, Gap, InlineSelect, useCountdown, ImagePlaceholder,
});
