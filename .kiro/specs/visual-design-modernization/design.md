# Design Document: Visual Design Modernization

## Overview

This document describes the technical design for modernizing the Latvian Listening Library (`latvian-listening-library/web/`). The app is a static single-page application served by Python's `http.server` locally and Fly.io in production. The stack is strictly vanilla HTML/CSS/JS — no framework, no bundler, no build step.

The modernization touches every layer of the three-file app:

- **`styles.css`** — extended with a full design token system, dark mode, skeleton animations, responsive breakpoints, and component styles for the custom audio player, sticky player, and progress indicators.
- **`index.html`** — restructured markup for the custom audio player, sticky player, skeleton placeholders, empty states, theme toggle, and progress bar; semantic HTML elements throughout.
- **`app.js`** — reorganized into a module-pattern IIFE with clearly separated concerns: state management, DOM rendering, audio controller, progress tracker, theme manager, and skeleton/empty-state helpers.

All existing functionality is preserved. The `catalog.json` schema gains two optional fields (`waveform_url` and `exam`) to support waveform visualization and exam-readiness tracking.

---

## Architecture

### File Organization

The three files remain at `latvian-listening-library/web/`. No new files are introduced to the web directory (waveform data is fetched from URLs referenced in `catalog.json`).

```
latvian-listening-library/web/
  index.html      — restructured markup; no inline scripts or styles
  styles.css      — design tokens, component styles, dark mode, responsive, animations
  app.js          — IIFE module pattern; all JS logic
  catalog.json    — lesson metadata; gains optional waveform_url and exam fields
```

### Rendering Model

The app remains fully client-side. On load, `app.js`:

1. Reads `localStorage["theme"]` and applies `data-theme` to `<html>` **before** any paint (synchronous, top of script).
2. Shows sidebar skeleton placeholders immediately.
3. Fetches `catalog.json`; on success, replaces skeletons with real lesson buttons and auto-selects the first lesson.
4. On lesson selection, shows panel skeletons, then populates content synchronously from the already-fetched catalog entry.
5. Waveform data (if `waveform_url` is present) is fetched lazily on lesson selection.

### Module Pattern (IIFE)

Since there is no bundler, `app.js` uses a single top-level IIFE that exposes a minimal `window.__lll` test hook object for Playwright tests. Internal modules are plain object literals or closures:

```
(function () {
  const ThemeManager   = { ... }   // localStorage theme, data-theme attribute
  const State          = { ... }   // in-memory catalog, filtered list, selectedIndex
  const ProgressTracker = { ... }  // localStorage lll_completed, completion logic
  const AudioController = { ... }  // custom player, waveform, sticky player
  const SkeletonHelper  = { ... }  // show/hide skeleton states
  const Renderer        = { ... }  // renderMenu, selectItem, renderEmptyState
  const SearchHandler   = { ... }  // debounced search filter

  // Expose test hooks
  window.__lll = { selectItem, State, ProgressTracker, ThemeManager }
})();
```

---

## CSS Token System Design

All tokens are defined in `styles.css`. The existing primitive tokens (`--navy`, `--magenta`, etc.) are preserved. New tokens are added in layers.

### Spacing Scale (4px base)

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-7: 28px;
  --space-8: 32px;
}
```

### Type Scale

```css
:root {
  --text-xs:   0.75rem;    /* 12px */
  --text-sm:   0.875rem;   /* 14px */
  --text-base: 1rem;       /* 16px */
  --text-lg:   1.125rem;   /* 18px */
  --text-xl:   1.25rem;    /* 20px */
  --text-2xl:  1.5rem;     /* 24px */
  --text-3xl:  2rem;       /* 32px */
}
```

### Border Radius and Shadow

```css
:root {
  --radius-sm:  8px;
  --radius-md:  14px;
  --radius-lg:  20px;
  --radius-xl:  28px;
  --radius-pill: 999px;

  --shadow-sm:  0 2px 8px rgba(8, 47, 73, 0.08);
  --shadow-md:  0 8px 24px rgba(8, 47, 73, 0.10);
  --shadow-lg:  0 24px 70px rgba(8, 47, 73, 0.12);
}
```

### Semantic Color Tokens — Light Theme (`:root`)

```css
:root {
  --color-surface:        var(--paper);          /* #fffdf8 — page/card background */
  --color-surface-raised: rgba(255,253,248,0.94); /* elevated card */
  --color-text-primary:   var(--ink);            /* #173044 */
  --color-text-secondary: var(--muted);          /* #708496 */
  --color-accent:         var(--magenta);        /* #d60a4f */
  --color-border:         var(--line);           /* #d6e1e7 */
}
```

### Semantic Color Tokens — Dark Theme

Applied by both `@media (prefers-color-scheme: dark)` and `[data-theme="dark"]`. The `[data-theme="dark"]` selector has higher specificity and takes precedence when set explicitly. `[data-theme="light"]` re-declares the light values to override the media query.

```css
@media (prefers-color-scheme: dark) {
  :root {
    --color-surface:        #0d1b26;
    --color-surface-raised: #152333;
    --color-text-primary:   #e8f0f5;
    --color-text-secondary: #8aa4b8;
    --color-accent:         var(--magenta-soft);  /* #ff4f87 — brighter on dark */
    --color-border:         #2a3f52;
  }
}

[data-theme="dark"] {
  --color-surface:        #0d1b26;
  --color-surface-raised: #152333;
  --color-text-primary:   #e8f0f5;
  --color-text-secondary: #8aa4b8;
  --color-accent:         var(--magenta-soft);
  --color-border:         #2a3f52;
}

[data-theme="light"] {
  --color-surface:        var(--paper);
  --color-surface-raised: rgba(255,253,248,0.94);
  --color-text-primary:   var(--ink);
  --color-text-secondary: var(--muted);
  --color-accent:         var(--magenta);
  --color-border:         var(--line);
}
```

**Rationale for dark palette choices:**
- `#0d1b26` is a deep navy that harmonizes with the existing `--navy` brand color.
- `--magenta-soft` (`#ff4f87`) is used as the accent on dark backgrounds because `--magenta` (`#d60a4f`) does not meet 3:1 contrast against dark surfaces.
- Text colors are desaturated blue-grays rather than pure white to reduce eye strain.

### Skeleton Animation

```css
@keyframes shimmer {
  0%   { opacity: 0.5; }
  50%  { opacity: 1;   }
  100% { opacity: 0.5; }
}

.skeleton-line {
  background: var(--color-border);
  border-radius: var(--radius-sm);
  height: 14px;
  animation: shimmer 1.5s ease-in-out infinite;
}

.skeleton-line:nth-child(2) { width: 80%; }
.skeleton-line:nth-child(3) { width: 65%; }

@media (prefers-reduced-motion: reduce) {
  .skeleton-line {
    animation: none;
    opacity: 0.6;
  }
}
```

### Focus Ring

```css
:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}
```

Using `:focus-visible` ensures the ring appears for keyboard navigation but not mouse clicks, following modern best practice.

---

## Components and Interfaces

### Sidebar

The sidebar `<aside>` contains, in order:

1. **Brand block** — `<div class="brand">` with the `LV` mark and heading.
2. **Theme Toggle** — `<button id="theme-toggle">` with a sun/moon icon and `aria-label` that reflects the current theme.
3. **Search** — `<label for="search">` + `<input id="search" type="search">`.
4. **Level Sections** — `<nav id="menu">` containing `<section class="level-section">` elements, each with a `<button class="level-toggle">` and a `<div class="item-list">`.

Each lesson button inside `.item-list` has the structure:

```html
<button type="button" class="audio-item" data-lesson-id="...">
  <span class="play-icon" aria-hidden="true"></span>
  <span class="lesson-title">...</span>
  <span class="lesson-status">...</span>
  <span class="completion-dot" aria-hidden="true"></span>  <!-- shown when completed -->
</button>
```

The `.play-icon` is a CSS-only triangle (border trick), replacing the current `.play-dot::before` approach but keeping the same visual. The `.completion-dot` is a filled circle shown only when the lesson is in `lll_completed`.

**Skeleton state** (during catalog fetch): three `<div class="skeleton-item">` elements per level section, replaced by real buttons once the catalog resolves.

**Search empty state**: a `<p class="search-empty">` paragraph injected into `#menu` when the filtered list is empty.

### Audio Player

The native `<audio id="audio" controls>` is replaced with a custom player structure inside `.player-card`:

```html
<div class="audio-player" role="group" aria-label="Audio player">
  <button id="play-pause" type="button" aria-label="Play">
    <span class="icon-play" aria-hidden="true"></span>
  </button>
  <div class="progress-container">
    <canvas id="waveform-canvas" aria-hidden="true"></canvas>  <!-- optional overlay -->
    <input id="seek-bar" type="range" min="0" max="100" value="0"
           aria-label="Seek" step="1" />
  </div>
  <span id="time-display" aria-live="off">0:00 / 0:00</span>
</div>
<div id="audio-error" class="audio-error" hidden>
  Unable to load audio. Check your connection and try again.
</div>
<div id="playback-status" aria-live="polite" class="sr-only"></div>
<!-- Hidden native audio element — no controls attribute -->
<audio id="audio" preload="metadata"></audio>
```

The `<input type="range">` doubles as the seek bar and is keyboard-operable natively (arrow keys). `app.js` intercepts `keydown` on the seek bar to enforce the 1-second-per-keypress requirement by calling `audio.currentTime += 1` / `-= 1` and preventing the default range step.

The `#playback-status` `aria-live="polite"` region is updated with "Playing", "Paused", or "Track ended" on state changes.

### Waveform Visualizer

When `waveform_url` is present in the catalog entry, `app.js` fetches the JSON array of normalized amplitude values (0–1) and draws them onto `#waveform-canvas` using the Canvas 2D API. The canvas is positioned absolutely behind the seek bar via CSS, creating a visual overlay. The canvas is `aria-hidden="true"` — it is purely decorative.

If the waveform fetch fails or the field is absent, the canvas remains empty (transparent) and the seek bar renders normally.

### Sticky Player

A second, minimal player element is placed at the bottom of `<body>`:

```html
<div id="sticky-player" class="sticky-player" hidden aria-label="Sticky audio player">
  <button id="sticky-play-pause" type="button" aria-label="Play">
    <span class="icon-play" aria-hidden="true"></span>
  </button>
  <input id="sticky-seek" type="range" min="0" max="100" value="0" aria-label="Seek" />
  <span id="sticky-time" class="sticky-time">0:00</span>
</div>
```

An `IntersectionObserver` watches `.player-card`. When the player card exits the viewport on a mobile viewport (≤ 768px) and audio is playing, `hidden` is removed from `#sticky-player`. When the player card re-enters the viewport, `hidden` is restored. The sticky player shares the same underlying `<audio>` element — its controls mirror the main player state via the same `AudioController` event handlers.

### Text Panels

Each `<article class="text-panel">` gains:

- `overflow-y: auto` and a `max-height` so content scrolls independently.
- A `<div class="panel-body">` wrapper around the `<pre class="reading-text">` to allow the heading/divider to remain fixed while the body scrolls.
- The Markdown link (`<a id="lvLink">`) is hidden via `hidden` attribute when no URL is available, rather than pointing to `#`.

**Skeleton state**: three `<div class="skeleton-line">` elements inside `.panel-body`, shown while content is loading.

### Empty States

The Hero section gains a dedicated empty-state block:

```html
<div id="hero-empty" class="hero-empty">
  <h2>Select an audio item to start listening.</h2>
  <p>Choose a lesson from the sidebar to begin.</p>
  <div class="hero-ctas">
    <button type="button" class="cta-btn">Try today's 5-minute challenge.</button>
    <button type="button" class="cta-btn">Browse by real-life situation.</button>
  </div>
</div>
<div id="hero-content" hidden>
  <!-- lesson title, subtitle, status badge, progress bar -->
</div>
```

`#hero-empty` is shown on initial load and hidden once a lesson is selected. `#hero-content` is the inverse.

### Theme Toggle

```html
<button id="theme-toggle" type="button" aria-label="Switch to dark mode">
  <span class="icon-sun" aria-hidden="true">☀</span>
  <span class="icon-moon" aria-hidden="true">☽</span>
</button>
```

CSS shows/hides the sun or moon icon based on `[data-theme="dark"]` on `<html>`. The `aria-label` is updated by `ThemeManager.apply()` every time the theme changes.

### Progress Bar (Hero)

Inside `#hero-content`:

```html
<div class="level-progress">
  <div class="progress-track">
    <div id="level-progress-bar" class="progress-fill" role="progressbar"
         aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"
         style="width: 0%"></div>
  </div>
  <span id="level-progress-label">0 of 0 completed</span>
</div>
<div id="exam-readiness" class="exam-readiness" hidden>
  Exam readiness: <span id="exam-pct">0%</span> (estimated)
</div>
```

---

## Data Models

### Catalog Entry (extended)

The existing catalog schema gains two optional fields:

```json
{
  "id": "A1-29ac14e2da565172",
  "level": "A1",
  "title": "1.nodalja",
  "original_filename": "1.nodalja.mp3",
  "audio_url": "data/A1_klausisanas/audio/1.nodalja.mp3",
  "lv_text": "...",
  "en_text": "...",
  "lv_markdown_url": "data/A1_klausisanas/transcripts_lv/1.nodalja.lv.md",
  "en_markdown_url": "data/A1_klausisanas/translations_en/1.nodalja.en.md",
  "status": "completed",
  "transcription_status": "transcribed",
  "translation_status": "translated",
  "lesson_group": "1. nodaļa",
  "order": 1,
  "waveform_url": "data/A1_klausisanas/waveforms/1.nodalja.waveform.json",  // NEW, optional
  "exam": true  // NEW, optional boolean — marks exam-relevant lessons
}
```

Both new fields are optional. Existing catalog entries without them continue to work without modification.

### Waveform JSON Format

A waveform file is a JSON array of numbers in the range [0, 1], representing normalized amplitude samples at uniform time intervals:

```json
[0.12, 0.45, 0.78, 0.34, 0.91, ...]
```

The number of samples is variable. `app.js` resamples the array to fit the canvas width using linear interpolation.

### localStorage Keys

| Key | Type | Description |
|-----|------|-------------|
| `"theme"` | `"light"` \| `"dark"` | User's explicit theme preference |
| `"lll_completed"` | `{ [lessonId: string]: boolean }` | Completion map for all lessons |

### In-Memory State

```js
const State = {
  catalog: [],          // full catalog array from catalog.json
  filtered: [],         // filtered subset after search
  selectedIndex: -1,    // index into filtered[]
  isPlaying: false,     // audio playback state
  currentTime: 0,       // audio currentTime in seconds
  duration: 0,          // audio duration in seconds
  waveformData: null,   // Float32Array or null
};
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

This feature is primarily a UI/CSS modernization. Most acceptance criteria are configuration checks, layout checks, or specific state transitions that are best verified with example-based tests. However, several criteria involve logic that varies meaningfully with input and is worth verifying as properties.

**PBT applicability assessment**: The feature includes pure JavaScript functions (time formatter, search filter, completion threshold, progress ratio calculation, theme toggle logic) that have clear input/output behavior and benefit from property-based testing. CSS rendering and layout checks are not suitable for PBT and are covered by example-based Playwright tests instead.

### Property 1: Time formatter produces valid mm:ss output

*For any* non-negative integer number of seconds, the `formatTime(seconds)` function SHALL produce a string matching the pattern `\d+:\d{2}` (minutes colon two-digit seconds).

**Validates: Requirements 4.7**

### Property 2: Search filter is case-insensitive and complete

*For any* search query string `q` and catalog array, every lesson returned by `applyFilter(q)` SHALL contain `q.toLowerCase()` somewhere in its searchable fields (title, original_filename, level, status, lv_text, en_text), and no lesson that contains `q.toLowerCase()` in those fields SHALL be absent from the result.

**Validates: Requirements 3.2, 6.4**

### Property 3: Completion threshold at 80%

*For any* audio duration `d > 0` and current playback position `t`, the lesson SHALL be marked as completed if and only if `t / d >= 0.8`.

**Validates: Requirements 11.3**

### Property 4: Progress ratio correctness

*For any* completion state (a set of completed lesson IDs) and a catalog level, the progress bar `aria-valuenow` SHALL equal `Math.round((completedCount / totalCount) * 100)` and the label text SHALL be `"${completedCount} of ${totalCount} completed"`.

**Validates: Requirements 11.2**

### Property 5: Completion persistence round-trip

*For any* set of lesson IDs marked as completed, writing to `localStorage["lll_completed"]` and then reading it back SHALL produce an equivalent object (same keys mapped to `true`).

**Validates: Requirements 11.4**

### Property 6: Theme toggle flips theme and updates aria-label

*For any* current theme state (`"light"` or `"dark"`), activating the Theme_Toggle SHALL set `data-theme` on `<html>` to the opposite value, persist that value to `localStorage["theme"]`, and update the toggle's `aria-label` to `"Switch to dark mode"` when the new theme is light, or `"Switch to light mode"` when the new theme is dark.

**Validates: Requirements 8.3, 8.6, 8.7**

### Property 7: Unavailability message for missing transcript or translation

*For any* lesson where `lv_text` is absent, empty, or whitespace-only, the Latvian Text_Panel SHALL display "Latvian transcript is not available yet." and SHALL NOT display the empty string or a blank panel. The same property holds symmetrically for `en_text` and the English Text_Panel.

**Validates: Requirements 5.5, 5.6**

### Property 8: Active lesson indicator in sidebar

*For any* lesson selected via `selectItem(index)`, the sidebar button corresponding to that lesson SHALL have the `active` class applied, and no other lesson button SHALL have the `active` class simultaneously.

**Validates: Requirements 3.6**

---

## Error Handling

### Catalog Fetch Failure

If `fetch("catalog.json")` rejects or returns a non-OK status, `app.js` catches the error and:

1. Hides `.player-card` and both `.text-panel` elements.
2. Shows the catalog-error empty state in the Hero with the message "Catalog not ready. Run the build script after processing audio."
3. Logs the error to `console.error`.
4. Does not attempt to render the sidebar lesson list.

### Audio Load Failure

If the `<audio>` element fires an `error` event:

1. `#audio-error` is shown (removes `hidden`).
2. The play/pause button is disabled.
3. The `#playback-status` aria-live region is updated with "Audio failed to load."

### Waveform Fetch Failure

If the waveform JSON fetch fails (network error, 404, or invalid JSON):

1. The canvas remains empty (no visual).
2. The seek bar renders normally.
3. Audio playback is unaffected.
4. The error is logged to `console.warn` (non-critical).

### localStorage Unavailability

All `localStorage` reads and writes are wrapped in a `try/catch`. If `localStorage` is unavailable (e.g., private browsing with storage blocked):

1. Theme defaults to `prefers-color-scheme`.
2. Completion state is tracked in-memory only (lost on reload).
3. No uncaught errors are thrown.

---

## Testing Strategy

### Existing Tests

The existing Playwright tests in `tests/playwright/release-regression.spec.js` target the A2 Exam App (`/latvian-a2-exam-app/`), not the Listening Library. They are unaffected by this change.

### New Test File

A new Playwright test file is added at `tests/playwright/listening-library.spec.js`. It uses a separate `baseURL` pointing to the listening library (`http://localhost:4173/latvian-listening-library/web/`). The Playwright config is extended with a second project entry for this path.

### Unit Tests (Property-Based)

Property-based tests for the pure JavaScript functions in `app.js` are written using [fast-check](https://github.com/dubzzz/fast-check) (a well-maintained JS PBT library). These tests run in Node.js without a browser, targeting the exported logic functions.

Since `app.js` uses an IIFE, the pure functions (`formatTime`, `applyFilter`, `isCompleted`, `calcProgress`) are extracted into a small `lib.js` module that is `require()`-able in tests and also `<script>`-included in `index.html` before `app.js`. This keeps the no-bundler constraint while making the logic testable.

**Test file**: `tests/listening-library/lib.test.js`

Each property test runs a minimum of **100 iterations** via fast-check's default configuration.

```js
// Tag format: Feature: visual-design-modernization, Property N: <property text>
```

#### Property 1: Time formatter produces valid mm:ss output
```js
// Feature: visual-design-modernization, Property 1: formatTime produces valid mm:ss output
fc.assert(fc.property(fc.nat(86400), (seconds) => {
  const result = formatTime(seconds);
  return /^\d+:\d{2}$/.test(result);
}), { numRuns: 100 });
```

#### Property 2: Search filter is case-insensitive and complete
```js
// Feature: visual-design-modernization, Property 2: search filter is case-insensitive and complete
fc.assert(fc.property(fc.array(lessonArb), fc.string(), (catalog, query) => {
  const results = applyFilter(catalog, query);
  const q = query.toLowerCase();
  // All results match
  const allMatch = results.every(item => searchableText(item).includes(q));
  // No matching item is missing
  const noneOmitted = catalog
    .filter(item => searchableText(item).includes(q))
    .every(item => results.some(r => r.id === item.id));
  return allMatch && noneOmitted;
}), { numRuns: 100 });
```

#### Property 3: Completion threshold at 80%
```js
// Feature: visual-design-modernization, Property 3: completion threshold at 80%
fc.assert(fc.property(
  fc.float({ min: 0.01, max: 3600 }),  // duration
  fc.float({ min: 0, max: 1 }).map(r => r),  // ratio
  (duration, ratio) => {
    const currentTime = ratio * duration;
    const shouldComplete = ratio >= 0.8;
    return isCompleted(currentTime, duration) === shouldComplete;
  }
), { numRuns: 100 });
```

#### Property 4: Progress ratio correctness
```js
// Feature: visual-design-modernization, Property 4: progress ratio correctness
fc.assert(fc.property(
  fc.array(fc.string({ minLength: 1 }), { minLength: 1, maxLength: 50 }),  // lesson IDs
  fc.nat().map(n => n % 51),  // completedCount <= total
  (ids, completedCount) => {
    const completed = Object.fromEntries(ids.slice(0, completedCount).map(id => [id, true]));
    const { valuenow, label } = calcProgress(ids, completed);
    const expected = Math.round((completedCount / ids.length) * 100);
    return valuenow === expected && label === `${completedCount} of ${ids.length} completed`;
  }
), { numRuns: 100 });
```

#### Property 5: Completion persistence round-trip
```js
// Feature: visual-design-modernization, Property 5: completion persistence round-trip
fc.assert(fc.property(
  fc.array(fc.string({ minLength: 1 }), { maxLength: 30 }),
  (ids) => {
    const completedMap = Object.fromEntries(ids.map(id => [id, true]));
    const serialized = JSON.stringify(completedMap);
    const deserialized = JSON.parse(serialized);
    return ids.every(id => deserialized[id] === true);
  }
), { numRuns: 100 });
```

#### Property 6: Theme toggle flips theme and updates aria-label
```js
// Feature: visual-design-modernization, Property 6: theme toggle flips theme and updates aria-label
fc.assert(fc.property(
  fc.constantFrom('light', 'dark'),
  (initialTheme) => {
    const result = toggleTheme(initialTheme);
    const expectedTheme = initialTheme === 'light' ? 'dark' : 'light';
    const expectedLabel = expectedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
    return result.theme === expectedTheme && result.ariaLabel === expectedLabel;
  }
), { numRuns: 100 });
```

#### Property 7: Unavailability message for missing transcript or translation
```js
// Feature: visual-design-modernization, Property 7: unavailability message for missing content
fc.assert(fc.property(
  fc.oneof(fc.constant(null), fc.constant(''), fc.constant('   '), fc.constant(undefined)),
  (text) => {
    const result = resolveText(text, 'lv');
    return result === 'Latvian transcript is not available yet.';
  }
), { numRuns: 100 });
```

#### Property 8: Active lesson indicator in sidebar
```js
// Feature: visual-design-modernization, Property 8: active lesson indicator in sidebar
fc.assert(fc.property(
  fc.array(lessonArb, { minLength: 1, maxLength: 20 }),
  fc.nat(),
  (lessons, rawIndex) => {
    const index = rawIndex % lessons.length;
    const activeIds = getActiveIds(lessons, index);
    return activeIds.length === 1 && activeIds[0] === lessons[index].id;
  }
), { numRuns: 100 });
```

### Playwright Integration Tests

The Playwright tests cover the four component states from Requirement 12, responsive layout, sticky player, and accessibility:

| Test | Type | Viewport |
|------|------|----------|
| Empty catalog → empty state + disabled player | Example | 1280×800 |
| Mock catalog + selectItem(0) → hero/player/panels populated | Example | 1280×800 |
| Delayed catalog fetch (500ms) → skeleton visible | Example | 1280×800 |
| data-theme="dark" pre-set → dark tokens applied | Example | 1280×800 |
| axe-core zero critical/serious violations (all 4 states) | Integration | 1280×800 |
| Mobile smoke test: Sticky_Player visible during playback | Integration | 375×812 |
| Two-column layout at >1200px | Example | 1440×900 |
| Stacked layout at ≤768px | Example | 375×812 |
| No horizontal scroll at 320px | Example | 320×568 |
| Theme toggle persists to localStorage | Example | 1280×800 |
| Keyboard seek bar: ArrowRight advances 1s | Example | 1280×800 |

### Accessibility Testing

axe-core is integrated into the Playwright tests via `@axe-core/playwright`. Each of the four component states is checked for zero `critical` or `serious` violations. The tests run in the CI pipeline alongside the existing regression suite.

### Reduced-Motion Testing

A Playwright test uses `page.emulateMedia({ reducedMotion: 'reduce' })` to verify that skeleton animations are disabled and no CSS transitions fire.
