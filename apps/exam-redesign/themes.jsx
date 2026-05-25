// themes.jsx — applies tweak state to <html> dataset attributes.
// Theme tokens live in theme.css, keyed off these attributes.

const THEMES = [
  { id: "valsts",   label: "Valsts",   sub: "Oficiāls", desc: "Carmine + navy on cream. State-document feel." },
  { id: "klusums",  label: "Klusums",  sub: "Mierīgs",  desc: "Sage + clay on warm white. Low-anxiety." },
  { id: "studija",  label: "Studija",  sub: "Redakcija", desc: "Editorial B&W + gold. Sharp, archival." },
];

const DENSITY  = ["compact", "comfy", "spacious"];
const SCALES   = ["s", "m", "l"];
const TYPESETS = [
  { id: "serif-sans", label: "Serif + Sans" },
  { id: "sans-sans",  label: "All sans"     },
  { id: "display",    label: "Display serif" },
];
const CARDLAYOUTS = [
  { id: "stacked", label: "Stacked" },
  { id: "split",   label: "Split"   },
  { id: "compact", label: "Compact" },
];
const TIMERS = [
  { id: "bar",   label: "Top bar"   },
  { id: "ring",  label: "Ring"      },
  { id: "pill",  label: "Pill chip" },
];

function applyTheme(t) {
  const r = document.documentElement;
  r.dataset.theme     = t.theme;
  r.dataset.mode      = t.dark ? "dark" : "light";
  r.dataset.density   = t.density;
  r.dataset.typescale = t.typeScale;
  r.dataset.typeset   = t.typeSet;
  r.dataset.cardlayout = t.cardLayout;
  r.dataset.timer     = t.timer;
}

Object.assign(window, { THEMES, DENSITY, SCALES, TYPESETS, CARDLAYOUTS, TIMERS, applyTheme });
