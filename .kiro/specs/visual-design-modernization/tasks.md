# Implementation Plan: Visual Design Modernization

## Overview

Modernize the Latvian Listening Library (`latvian-listening-library/web/`) in vanilla HTML/CSS/JS. The work is layered: CSS tokens first, then the pure-logic `lib.js` module, then `index.html` restructure, then `app.js` refactor, and finally tests. Each task leaves the app in a working state.

New files introduced:
- `latvian-listening-library/web/lib.js` — pure functions, included via `<script>` before `app.js`
- `tests/listening-library/lib.test.js` — fast-check property-based unit tests
- `tests/playwright/listening-library.spec.js` — Playwright integration + accessibility tests

`fast-check` must be added as a devDependency (`npm install --save-dev fast-check`).

---

## Tasks

- [x] 1. Extend CSS token system in `styles.css`
  - [x] 1.1 Add spacing scale, type scale, radius, and shadow tokens to `:root`
    - Append `--space-1` through `--space-8` (4px base), `--text-xs` through `--text-3xl`, `--radius-sm/md/lg/xl/pill`, and `--shadow-sm/md/lg` to the existing `:root` block in `styles.css`
    - Preserve all existing primitive tokens (`--navy`, `--magenta`, `--paper`, `--ink`, `--muted`, `--line`, `--success`, `--warn`, `--danger`, `--navy-deep`, `--magenta-soft`, `--ice`)
    - _Requirements: 1.1, 2.4_

  - [x] 1.2 Add semantic color tokens with light, dark-media, and data-theme overrides
    - Add `--color-surface`, `--color-surface-raised`, `--color-text-primary`, `--color-text-secondary`, `--color-accent`, `--color-border` with light values in `:root`
    - Add `@media (prefers-color-scheme: dark) { :root { … } }` block remapping all six tokens to dark values
    - Add `[data-theme="dark"] { … }` block with the same dark values (higher specificity override)
    - Add `[data-theme="light"] { … }` block re-declaring light values to override the media query
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 8.1_

- [x] 2. Apply typography, spacing, and component styles in `styles.css`
  - [x] 2.1 Update body font stack, base size, and line-height; apply token-based spacing to cards
    - Change `font-family` on `body` to `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
    - Set `font-size: 1rem` and `line-height: 1.6` on `body`
    - Replace hard-coded `padding` values on `.hero`, `.player-card`, and `.text-panel` with `var(--space-4)` (minimum); use `var(--space-7)` for hero to match design
    - Set gap between `.item-list` items to `var(--space-2)` and vertical gap in `.reader` to `var(--space-4)`
    - _Requirements: 2.1, 2.3, 2.5, 2.6_

  - [x] 2.2 Apply semantic color tokens to existing component selectors
    - Replace hard-coded color values in `.hero`, `.player-card`, `.text-panel`, `.sidebar`, `body` background, and text elements with the new semantic tokens (`--color-surface`, `--color-surface-raised`, `--color-text-primary`, `--color-text-secondary`, `--color-accent`, `--color-border`)
    - Update `.reading-text` to use `font-size: var(--text-lg)` and `line-height: 1.72`
    - _Requirements: 2.2, 5.2_

  - [x] 2.3 Add skeleton animation, focus ring, and reduced-motion rules
    - Add `@keyframes shimmer` (opacity 0.5 → 1 → 0.5, 1.5s) and `.skeleton-line` / `.skeleton-item` styles using `var(--color-border)` and `var(--radius-sm)`
    - Add `:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }` rule
    - Add `@media (prefers-reduced-motion: reduce)` block disabling `.skeleton-line` animation and all CSS transitions
    - _Requirements: 7.4, 7.5, 10.1, 10.5_

  - [x] 2.4 Add custom audio player, sticky player, progress bar, and responsive styles
    - Add styles for `.audio-player`, `#play-pause`, `.progress-container`, `#seek-bar`, `#waveform-canvas` (absolute overlay), `#time-display`, `#audio-error`, `.sticky-player` (fixed bottom, hidden by default, shown on mobile ≤768px)
    - Add `.level-progress`, `.progress-track`, `.progress-fill` styles for the hero progress bar
    - Add `.hero-empty`, `.hero-ctas`, `.cta-btn`, `.search-empty`, `.completion-dot`, `.sr-only` styles
    - Update responsive breakpoints: `min-width: 769px` (side-by-side sidebar+reader), `min-width: 901px` (two-column text panels), `min-width: 1201px` (fixed sidebar width 300–390px); mobile-first baseline for ≤768px (stacked, sidebar max-height 52vh, touch targets ≥44×44px)
    - _Requirements: 4.1, 4.8, 5.1, 5.9, 5.10, 9.1, 9.2, 9.3, 9.5, 9.6, 9.7, 11.2_

- [x] 3. Create `lib.js` with pure logic functions
  - [x] 3.1 Implement `formatTime`, `applyFilter`, `isCompleted`, `calcProgress`, `resolveText`, `toggleTheme`, and `getActiveIds`
    - Create `latvian-listening-library/web/lib.js` as a plain script (no ES module syntax — must work with `<script src>` and `require()`)
    - `formatTime(seconds)` → `"m:ss"` string (e.g., `formatTime(75)` → `"1:15"`)
    - `applyFilter(catalog, query)` → filtered array; searches title, original_filename, level, status, lv_text, en_text case-insensitively
    - `isCompleted(currentTime, duration)` → boolean; true iff `duration > 0 && currentTime / duration >= 0.8`
    - `calcProgress(lessonIds, completedMap)` → `{ valuenow, label }` where `valuenow = Math.round(completedCount / total * 100)` and `label = "${completedCount} of ${total} completed"`
    - `resolveText(text, lang)` → returns text if non-empty/non-whitespace; otherwise returns `"Latvian transcript is not available yet."` (lang=`"lv"`) or `"English translation is not available yet."` (lang=`"en"`)
    - `toggleTheme(currentTheme)` → `{ theme, ariaLabel }` where theme flips light↔dark and ariaLabel is `"Switch to light mode"` or `"Switch to dark mode"` accordingly
    - `getActiveIds(lessons, selectedIndex)` → array containing only `lessons[selectedIndex].id`
    - Export via `if (typeof module !== 'undefined') module.exports = { … }` for Node.js `require()` compatibility
    - _Requirements: 3.2, 4.7, 5.5, 5.6, 8.3, 8.6, 8.7, 11.3, 11.4_

- [x] 4. Restructure `index.html`
  - [x] 4.1 Add `lib.js` script tag, theme-toggle button, and skeleton placeholders to sidebar
    - Add `<script src="lib.js"></script>` before `<script src="app.js"></script>`
    - Add `<button id="theme-toggle" type="button" aria-label="Switch to dark mode">` with sun/moon icon spans inside `.sidebar`, after the brand block
    - Replace the static `<nav id="menu">` content with two `<section class="level-section">` stubs each containing three `<div class="skeleton-item">` placeholders (real items rendered by JS)
    - _Requirements: 3.7, 8.2, 8.6, 8.7, 10.3, 10.4_

  - [x] 4.2 Replace native `<audio controls>` with custom player markup and sticky player
    - Inside `.player-card`, replace `<audio id="audio" controls>` with the custom player structure: `<div class="audio-player" role="group" aria-label="Audio player">` containing `#play-pause` button, `.progress-container` with `#waveform-canvas` and `#seek-bar` range input, and `#time-display` span
    - Add `<div id="audio-error" hidden>` error message block and `<div id="playback-status" aria-live="polite" class="sr-only">` region
    - Add bare `<audio id="audio" preload="metadata">` (no controls attribute) after the custom player div
    - Add `<div id="sticky-player" class="sticky-player" hidden aria-label="Sticky audio player">` at the bottom of `<body>` with `#sticky-play-pause`, `#sticky-seek`, and `#sticky-time`
    - _Requirements: 4.1, 4.2, 4.6, 4.7, 4.8, 4.9, 10.2, 10.3, 10.7, 10.8_

  - [x] 4.3 Restructure Hero section with empty state, hero content, and progress bar markup
    - Replace the existing `.hero` content with two sibling divs: `#hero-empty` (shown on load, contains heading, supporting text, and two `.cta-btn` buttons) and `#hero-content` (hidden on load, contains `#title`, `#subtitle`, `#statusBadge`, `.level-progress` with `#level-progress-bar` progressbar and `#level-progress-label`, and `#exam-readiness` div)
    - Update Text_Panel `<article>` elements: add `overflow-y: auto` via class, wrap `<pre class="reading-text">` in `<div class="panel-body">`, add three `<div class="skeleton-line">` elements inside each `.panel-body` (hidden by default), update Markdown links to use `hidden` attribute instead of `href="#"`
    - Ensure all semantic elements are correct: `<aside>` for sidebar, `<main>` for reader, `<article>` for text panels, `<nav>` for menu, `<section>` for groupings
    - _Requirements: 5.3, 5.7, 5.8, 6.1, 6.2, 6.3, 10.6, 11.2, 11.6_

- [ ] 5. Refactor `app.js` into IIFE module pattern
  - [x] 5.1 Implement `ThemeManager` and `State` modules; apply theme before paint
    - Wrap all existing code in a top-level IIFE `(function () { … })();`
    - Implement `ThemeManager = { apply(theme), toggle(), init() }`: `init()` reads `localStorage["theme"]` synchronously at the top of the IIFE (before any DOM manipulation), sets `data-theme` on `<html>`, and updates `#theme-toggle` aria-label using `toggleTheme()` from `lib.js`; wrap all localStorage access in try/catch
    - Implement `State = { catalog, filtered, selectedIndex, isPlaying, currentTime, duration, waveformData }` as a plain object
    - Wire `#theme-toggle` click to `ThemeManager.toggle()`
    - Expose `window.__lll = { selectItem, State, ProgressTracker, ThemeManager }` at the end of the IIFE
    - _Requirements: 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 12.4_

  - [x] 5.2 Implement `ProgressTracker` module
    - Implement `ProgressTracker = { load(), save(id), isCompleted(id), getCompleted(), updateUI() }`: `load()` reads `localStorage["lll_completed"]` (try/catch); `save(id)` sets `completed[id] = true`, writes back to localStorage, then calls `updateUI()`; `updateUI()` updates completion dots on sidebar buttons, updates `#level-progress-bar` aria-valuenow and `#level-progress-label` text using `calcProgress()` from `lib.js`, and shows/hides `#exam-readiness`
    - Wire `<audio>` `timeupdate` event to call `ProgressTracker.save(item.id)` when `isCompleted(audio.currentTime, audio.duration)` returns true (using `isCompleted` from `lib.js`)
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [x] 5.3 Implement `SkeletonHelper` and `Renderer` modules
    - Implement `SkeletonHelper = { showSidebar(), hideSidebar(), showPanels(), hidePanels() }`: sidebar skeletons are the `.skeleton-item` divs in each `.item-list`; panel skeletons are the `.skeleton-line` divs inside each `.panel-body`
    - Implement `Renderer = { renderMenu(filtered, selectedIndex, completed), selectItem(index), renderEmptyState(type) }`: `renderMenu` builds lesson buttons using the structure from the design (`.play-icon`, `.lesson-title`, `.lesson-status`, `.completion-dot`), applies `active` class to the selected item only, and injects a `.search-empty` paragraph when filtered is empty; `selectItem` shows `#hero-content`, hides `#hero-empty`, populates `#title`/`#subtitle`/`#statusBadge`, calls `SkeletonHelper.showPanels()` then synchronously populates panels using `resolveText()` from `lib.js`, hides/shows Markdown links via `hidden` attribute; `renderEmptyState("catalog-error")` hides `.player-card` and both `.text-panel` elements and shows the error message in `#hero-empty`
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 6.1, 6.4, 6.5, 7.1, 7.2, 7.3, 12.1, 12.2, 12.3_

  - [x] 5.4 Implement `AudioController` module with custom player, waveform, and sticky player
    - Implement `AudioController = { init(), play(), pause(), seek(ratio), updateUI(), loadWaveform(url), initStickyPlayer() }`: `init()` wires `#play-pause` click, `#seek-bar` input/change, `<audio>` timeupdate/ended/error events; `updateUI()` updates `#seek-bar` value, `#time-display` using `formatTime()` from `lib.js`, `#playback-status` aria-live text ("Playing"/"Paused"/"Track ended"), and `#play-pause` aria-label; `loadWaveform(url)` fetches waveform JSON and draws onto `#waveform-canvas` using Canvas 2D API (bars), falls back silently on error; `initStickyPlayer()` creates an `IntersectionObserver` on `.player-card` that shows/hides `#sticky-player` when the card exits/enters the viewport on ≤768px viewports; sticky controls mirror main player state
    - Wire `#seek-bar` keydown to advance/rewind `audio.currentTime` by 1 second on ArrowRight/ArrowLeft and prevent default
    - Show `#audio-error` and disable `#play-pause` on `<audio>` error event
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 10.7, 10.8_

  - [x] 5.5 Implement `SearchHandler` and wire catalog fetch with skeleton/error states
    - Implement `SearchHandler = { init() }`: debounce `#search` input event by 300ms; on each input call `applyFilter(State.catalog, query)` from `lib.js`, update `State.filtered`, call `Renderer.renderMenu()`, and call `Renderer.selectItem(0)` if results exist
    - Update catalog `fetch` flow: call `SkeletonHelper.showSidebar()` immediately; on success call `SkeletonHelper.hideSidebar()` then `Renderer.renderMenu()` then `Renderer.selectItem(0)`; on failure call `Renderer.renderEmptyState("catalog-error")`
    - _Requirements: 3.1, 3.2, 3.7, 6.4, 6.5, 7.1, 12.3_

- [~] 6. Checkpoint — verify the app works end-to-end
  - Ensure all tests pass, ask the user if questions arise.
  - Serve the app locally (`python3 server.py`) and manually verify: catalog loads, lessons render, custom player plays audio, dark mode toggle works, sticky player appears on mobile viewport, skeleton states show and hide, empty states display correctly.

- [ ] 7. Write property-based unit tests in `tests/listening-library/lib.test.js`
  - [ ]* 7.1 Write property test for `formatTime` (Property 1)
    - Install `fast-check` as a devDependency: `npm install --save-dev fast-check`
    - Create `tests/listening-library/lib.test.js`; `require` lib.js functions and fast-check
    - **Property 1: formatTime produces valid mm:ss output**
    - **Validates: Requirements 4.7**
    - Use `fc.nat(86400)` as input; assert result matches `/^\d+:\d{2}$/`; `numRuns: 100`

  - [ ]* 7.2 Write property test for `applyFilter` (Property 2)
    - **Property 2: Search filter is case-insensitive and complete**
    - **Validates: Requirements 3.2, 6.4**
    - Use `fc.array(lessonArb)` and `fc.string()` as inputs; assert all results contain the lowercased query and no matching item is absent; `numRuns: 100`

  - [ ]* 7.3 Write property test for `isCompleted` (Property 3)
    - **Property 3: Completion threshold at 80%**
    - **Validates: Requirements 11.3**
    - Use `fc.float({ min: 0.01, max: 3600 })` for duration and `fc.float({ min: 0, max: 1 })` for ratio; assert `isCompleted(ratio * duration, duration) === (ratio >= 0.8)`; `numRuns: 100`

  - [ ]* 7.4 Write property test for `calcProgress` (Property 4)
    - **Property 4: Progress ratio correctness**
    - **Validates: Requirements 11.2**
    - Use `fc.array(fc.string({ minLength: 1 }), { minLength: 1, maxLength: 50 })` for IDs and a bounded nat for completedCount; assert `valuenow === Math.round(completedCount / total * 100)` and label matches `"${n} of ${total} completed"`; `numRuns: 100`

  - [ ]* 7.5 Write property test for completion persistence round-trip (Property 5)
    - **Property 5: Completion persistence round-trip**
    - **Validates: Requirements 11.4**
    - Use `fc.array(fc.string({ minLength: 1 }), { maxLength: 30 })` for IDs; assert `JSON.parse(JSON.stringify(completedMap))[id] === true` for all IDs; `numRuns: 100`

  - [ ]* 7.6 Write property test for `toggleTheme` (Property 6)
    - **Property 6: Theme toggle flips theme and updates aria-label**
    - **Validates: Requirements 8.3, 8.6, 8.7**
    - Use `fc.constantFrom('light', 'dark')` as input; assert result.theme is the opposite value and result.ariaLabel matches the expected string; `numRuns: 100`

  - [ ]* 7.7 Write property test for `resolveText` (Property 7)
    - **Property 7: Unavailability message for missing transcript or translation**
    - **Validates: Requirements 5.5, 5.6**
    - Use `fc.oneof(fc.constant(null), fc.constant(''), fc.constant('   '), fc.constant(undefined))` as input; assert `resolveText(text, 'lv')` returns `"Latvian transcript is not available yet."` and `resolveText(text, 'en')` returns `"English translation is not available yet."`; `numRuns: 100`

  - [ ]* 7.8 Write property test for `getActiveIds` (Property 8)
    - **Property 8: Active lesson indicator in sidebar**
    - **Validates: Requirements 3.6**
    - Use `fc.array(lessonArb, { minLength: 1, maxLength: 20 })` and `fc.nat()` as inputs; assert `getActiveIds(lessons, index % lessons.length)` returns an array of length 1 containing only `lessons[index].id`; `numRuns: 100`

- [ ] 8. Write Playwright integration and accessibility tests in `tests/playwright/listening-library.spec.js`
  - [ ]* 8.1 Add listening-library project to Playwright config and write empty-catalog test
    - Extend `playwright.config.js` (or create it if absent) with a second project entry: `{ name: 'listening-library', use: { baseURL: 'http://localhost:4173/latvian-listening-library/web/' } }`
    - Create `tests/playwright/listening-library.spec.js`
    - Test: empty catalog → `#hero-empty` visible, `.player-card` hidden or disabled
    - _Requirements: 6.1, 6.2, 6.3, 12.1_

  - [ ]* 8.2 Write mock catalog + selectItem(0) test
    - Test: intercept `catalog.json` with a mock entry; call `window.__lll.selectItem(0)`; assert `#title` text matches mock title, `#audio` has non-empty `src`, both text panels show content or unavailability messages
    - _Requirements: 5.3, 5.5, 5.6, 12.2_

  - [ ]* 8.3 Write delayed catalog fetch skeleton test
    - Test: intercept `catalog.json` with a 500ms delay; assert `.skeleton-item` elements are visible before the response resolves; assert they are replaced by real buttons after
    - _Requirements: 7.1, 12.3_

  - [ ]* 8.4 Write dark-mode pre-set test
    - Test: set `data-theme="dark"` on `<html>` before navigation; assert computed `background-color` of `.hero` matches the dark surface token value
    - _Requirements: 1.5, 8.1, 12.4_

  - [ ]* 8.5 Write axe-core accessibility tests for all four component states
    - Install `@axe-core/playwright` if not present; import `checkA11y` in the test file
    - Run axe-core in each of the four states (empty catalog, lesson selected, skeleton visible, dark mode); assert zero `critical` or `serious` violations
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 12.5_

  - [ ]* 8.6 Write mobile sticky-player smoke test
    - Test at 375×812px viewport: load app with a mock catalog, trigger audio playback, scroll `.player-card` out of view; assert `#sticky-player` bounding box is within the visible viewport and is not hidden
    - _Requirements: 4.8, 9.4, 12.6_

  - [ ]* 8.7 Write responsive layout tests (two-column, stacked, no horizontal scroll)
    - Test at 1440×900px: assert `.content-grid` has two columns (text panels side by side)
    - Test at 375×812px: assert `.app-shell` is single-column (sidebar stacked above reader)
    - Test at 320×568px: assert `document.body.scrollWidth <= 320` (no horizontal scroll)
    - _Requirements: 5.9, 5.10, 9.1, 9.2, 9.3, 9.7_

  - [ ]* 8.8 Write theme-toggle persistence and keyboard seek tests
    - Test: click `#theme-toggle`; assert `localStorage.getItem("theme")` equals `"dark"` and `<html>` has `data-theme="dark"`
    - Test: focus `#seek-bar`, press ArrowRight; assert `audio.currentTime` increased by 1 second
    - _Requirements: 8.3, 8.4, 10.8_

- [~] 9. Final checkpoint — run full test suite
  - Ensure all tests pass, ask the user if questions arise.
  - Run `npx playwright test tests/playwright/listening-library.spec.js` and `node --test tests/listening-library/lib.test.js` (or equivalent); fix any failures before marking complete.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- `lib.js` uses `if (typeof module !== 'undefined') module.exports = { … }` so it works both as a browser `<script>` and as a Node.js `require()` target — no bundler needed
- CSS changes are additive: existing tokens and selectors are preserved; new tokens extend `:root`
- The `window.__lll` test hook is the bridge between Playwright tests and the IIFE internals
- Checkpoints at tasks 6 and 9 ensure incremental validation at natural break points
- Property tests validate universal correctness; Playwright tests validate specific states and layout

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "2.2"] },
    { "id": 3, "tasks": ["2.3", "2.4", "3.1"] },
    { "id": 4, "tasks": ["4.1"] },
    { "id": 5, "tasks": ["4.2", "4.3"] },
    { "id": 6, "tasks": ["5.1"] },
    { "id": 7, "tasks": ["5.2", "5.3"] },
    { "id": 8, "tasks": ["5.4", "5.5"] },
    { "id": 9, "tasks": ["7.1", "7.2", "7.3", "7.4", "7.5", "7.6", "7.7", "7.8"] },
    { "id": 10, "tasks": ["8.1"] },
    { "id": 11, "tasks": ["8.2", "8.3", "8.4", "8.5", "8.6", "8.7", "8.8"] }
  ]
}
```
