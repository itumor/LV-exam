// app.jsx — main app, navigation state, Tweaks wiring.

const { useState, useEffect, useMemo, useCallback } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme":      "valsts",
  "dark":       false,
  "density":    "comfy",
  "typeScale":  "m",
  "typeSet":    "serif-sans",
  "cardLayout": "stacked",
  "timer":      "bar",
  "lang":       "lv"
}/*EDITMODE-END*/;

function Root() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  return (
    <I18nProvider lang={t.lang} setLang={(v) => setTweak('lang', v)}>
      <App t={t} setTweak={setTweak} />
    </I18nProvider>
  );
}

function App({ t, setTweak }) {

  // apply tokens to <html> whenever tweak state changes
  useEffect(() => { applyTheme(t); }, [t.theme, t.dark, t.density, t.typeScale, t.typeSet, t.cardLayout, t.timer]);

  // initial paint of theme attrs before first render
  useEffect(() => { applyTheme(t); /* eslint-disable-line */ }, []);

  // ── navigation state ──────────────────────────────────────────
  const [screenIdx, setScreenIdx] = useState(0);
  const screen = SCREENS[screenIdx];
  const part = screen.part;

  // ── per-screen answer state (kept flat by screen id) ──────────
  const [answers, setAnswers] = useState({
    "listening-1": Array(6).fill(null),
    "listening-2": Array(4).fill(null),
    "listening-3": Array(5).fill(null),
    "reading-1":   Array(4).fill(null),
    "reading-2":   {},
    "reading-3":   Array(5).fill(null),
    "writing-1":   Array(4).fill(""),
    "writing-3":   { text: "", checks: {} },
    "speaking-1":  Array(10).fill(null),
    "speaking-2":  { notes: "" },
    "speaking-3":  Array(3).fill(""),
  });
  const [w3Variant, setW3Variant] = useState("letter");

  const setAns = (id) => (a, b) => {
    setAnswers(prev => {
      const cur = prev[id];
      if (Array.isArray(cur)) {
        const nx = [...cur]; nx[a] = b; return { ...prev, [id]: nx };
      } else if (typeof cur === "object" && cur !== null && b === undefined) {
        return { ...prev, [id]: a }; // whole-object replace
      } else {
        return { ...prev, [id]: { ...cur, [a]: b } };
      }
    });
  };

  // ── timer (per-part countdown) ────────────────────────────────
  const partTimer = useMemo(() => {
    const p = PARTS.find(x => x.id === part);
    return p ? p.time * 60 : 0;
  }, [part]);

  const [timerLeft, setTimerLeft] = useState(partTimer);
  const [paused, setPaused] = useState(false);
  useEffect(() => { setTimerLeft(partTimer); }, [partTimer]);
  useEffect(() => {
    if (paused || part === "intro" || part === "submitted") return;
    if (timerLeft <= 0) return;
    const id = setInterval(() => setTimerLeft(v => Math.max(0, v - 1)), 1000);
    return () => clearInterval(id);
  }, [paused, part, timerLeft]);

  // ── nav helpers ──────────────────────────────────────────────
  const goto = useCallback((id) => {
    const i = SCREENS.findIndex(s => s.id === id);
    if (i >= 0) { setScreenIdx(i); window.scrollTo({ top: 0, behavior: "smooth" }); }
  }, []);
  const next = () => setScreenIdx(i => Math.min(SCREENS.length - 1, i + 1));
  const prev = () => setScreenIdx(i => Math.max(0, i - 1));

  // keyboard nav
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
      if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") prev();
      else if (e.key === " ") { e.preventDefault(); setPaused(p => !p); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ── footer derived state ─────────────────────────────────────
  const last = screenIdx === SCREENS.length - 1;
  const isIntro = screen.id === "intro";
  const isSubmitted = screen.id === "submitted";
  const isPartIntro = ["listen-intro", "read-intro", "write-intro", "speak-intro"].includes(screen.id);
  const lastInPart = !isIntro && !isPartIntro && !isSubmitted &&
    (SCREENS[screenIdx + 1]?.part !== part);

  // ── render current screen ────────────────────────────────────
  function renderScreen() {
    switch (screen.id) {
      case "intro":         return <IntroScreen onStart={() => goto("listen-intro")}/>;
      case "listen-intro":  return <SectionIntro part="listening" onStart={next}/>;
      case "read-intro":    return <SectionIntro part="reading"   prevPart="listening" onStart={next}/>;
      case "write-intro":   return <SectionIntro part="writing"   prevPart="reading"   onStart={next}/>;
      case "speak-intro":   return <SectionIntro part="speaking"  prevPart="writing"   onStart={next}/>;
      case "listening-1":   return <Listening1 state={answers["listening-1"]} set={setAns("listening-1")}/>;
      case "listening-2":   return <Listening2 state={answers["listening-2"]} set={setAns("listening-2")}/>;
      case "listening-3":   return <Listening3 state={answers["listening-3"]} set={setAns("listening-3")}/>;
      case "reading-1":     return <Reading1  state={answers["reading-1"]}  set={setAns("reading-1")}/>;
      case "reading-2":     return <Reading2  state={answers["reading-2"]}  set={setAns("reading-2")}/>;
      case "reading-3":     return <Reading3  state={answers["reading-3"]}  set={setAns("reading-3")}/>;
      case "writing-1":     return <Writing1  state={answers["writing-1"]}  set={setAns("writing-1")}/>;
      case "writing-3":     return <Writing3
                              state={answers["writing-3"]}
                              set={(v) => setAnswers(prev => ({...prev, "writing-3": v}))}
                              variant={w3Variant} setVariant={setW3Variant}/>;
      case "speaking-1":    return <Speaking1 state={answers["speaking-1"]} set={setAns("speaking-1")}/>;
      case "speaking-2":    return <Speaking2 state={answers["speaking-2"]} set={(v) => setAnswers(prev => ({...prev, "speaking-2": v}))}/>;
      case "speaking-3":    return <Speaking3 state={answers["speaking-3"]} set={setAns("speaking-3")}/>;
      case "submitted":     return <Submitted answers={answers} onRestart={() => { setScreenIdx(0); }}/>;
      default: return null;
    }
  }

  return (
    <div className="app">
      {!isIntro && !isSubmitted ? (
        <AppBar
          activePart={part}
          timerSecs={timerLeft}
          totalSecs={partTimer || 1}
          paused={paused}
          onPause={() => setPaused(p => !p)}
          onJump={(p) => goto(p)}
          onToggleTweaks={() => window.parent.postMessage({ type: "__edit_mode_request_toggle" }, "*")}
          mode={t.dark ? "dark" : "light"}
          onToggleMode={() => setTweak("dark", !t.dark)}
          lang={t.lang}
          onLang={(v) => setTweak("lang", v)}
        />
      ) : (
        <header className="appbar appbar--lite">
          <div className="appbar__inner">
            <a className="brand" href="#">
              <span className="brand__mark">A2</span>
              <span className="brand__text">
                <span className="brand__title">VVPP</span>
                <span className="brand__sub">Valsts valodas prasmes pārbaude · 2024</span>
              </span>
            </a>
            <div className="appbar__right">
              <LangSwitcher lang={t.lang} onLang={(v) => setTweak("lang", v)} />
              <button className="iconbtn" onClick={() => setTweak("dark", !t.dark)} aria-label="Mode">
                <Icon name={t.dark ? "sun" : "moon"} size={16}/>
              </button>
              <button className="iconbtn" type="button" onClick={() => window.parent.postMessage({ type: "__edit_mode_request_toggle" }, "*")} aria-label="Tweaks">
                <Icon name="cog" size={16}/>
              </button>
            </div>
          </div>
        </header>
      )}

      {!isIntro && !isSubmitted && !isPartIntro ? (
        <TaskBar activeScreen={screen.id} onJump={goto} screens={SCREENS}/>
      ) : <div className="taskbar-spacer" aria-hidden="true"/>}

      <div className="app__main">{renderScreen()}</div>

      {!isIntro && !isSubmitted ? (
        <FooterNav
          canPrev={screenIdx > 0}
          canNext={!last}
          onPrev={prev}
          onNext={next}
          primary={isPartIntro || lastInPart}
          lastInPart={lastInPart}
          lastOverall={last}
          hint={
            isPartIntro
              ? <I18nT k="chrome.foothint.intro" />
              : <I18nT k="chrome.foothint.partN" params={{
                  p: PARTS.findIndex(p => p.id === part),
                  n: SCREENS.filter(s => s.part === part && s.task).findIndex(s => s.id === screen.id) + 1
                }} />
          }
        />
      ) : null}

      <TweaksPanel>
        <TweakSection label="Direction" />
        <TweakRadio
          label="Theme"
          value={t.theme}
          options={THEMES.map(x => x.id)}
          onChange={(v) => setTweak("theme", v)}
        />
        <ThemeDescriber theme={t.theme} />
        <TweakToggle label="Dark mode" value={t.dark} onChange={(v) => setTweak("dark", v)} />

        <TweakSection label="Language" />
        <TweakRadio
          label="Interface"
          value={t.lang}
          options={LANGS.map(x => x.id)}
          onChange={(v) => setTweak("lang", v)}
        />

        <TweakSection label="Typography" />
        <TweakSelect
          label="Font pairing"
          value={t.typeSet}
          options={TYPESETS.map(x => ({ value: x.id, label: x.label }))}
          onChange={(v) => setTweak("typeSet", v)}
        />
        <TweakRadio
          label="Size"
          value={t.typeScale}
          options={["s", "m", "l"]}
          onChange={(v) => setTweak("typeScale", v)}
        />

        <TweakSection label="Layout" />
        <TweakRadio
          label="Density"
          value={t.density}
          options={["compact", "comfy", "spacious"]}
          onChange={(v) => setTweak("density", v)}
        />
        <TweakSelect
          label="Question cards"
          value={t.cardLayout}
          options={CARDLAYOUTS.map(x => ({ value: x.id, label: x.label }))}
          onChange={(v) => setTweak("cardLayout", v)}
        />
        <TweakSelect
          label="Timer style"
          value={t.timer}
          options={TIMERS.map(x => ({ value: x.id, label: x.label }))}
          onChange={(v) => setTweak("timer", v)}
        />

        <TweakSection label="Navigation" />
        <div className="twk-row">
          <span className="twk-lbl"><span>Jump to screen</span></span>
          <select
            value={screen.id}
            onChange={(e) => goto(e.target.value)}
            style={{
              padding: "6px 8px", borderRadius: 6, fontSize: 11,
              border: "1px solid rgba(0,0,0,.12)", background: "rgba(255,255,255,.6)"
            }}
          >
            {SCREENS.map((s, i) => (
              <option key={s.id} value={s.id}>
                {String(i + 1).padStart(2, "0")} · {s.id}
              </option>
            ))}
          </select>
        </div>
      </TweaksPanel>
    </div>
  );
}

function ThemeDescriber({ theme }) {
  const meta = THEMES.find(t => t.id === theme);
  if (!meta) return null;
  return (
    <div style={{
      padding: "8px 10px",
      borderRadius: 8,
      background: "rgba(0,0,0,.04)",
      fontSize: 11,
      color: "rgba(41,38,27,.7)",
      lineHeight: 1.45,
    }}>
      <strong style={{ color: "rgba(41,38,27,1)" }}>{meta.sub}</strong>
      <div>{meta.desc}</div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<Root />);
