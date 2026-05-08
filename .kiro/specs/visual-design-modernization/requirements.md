# Requirements Document

## Introduction

This feature modernizes the visual design of the Latvian A2 Listening Library — a static vanilla HTML/CSS/JS single-page application located at `latvian-listening-library/web/`. The goal is to make the product feel calm, polished, mobile-first, and motivating while preserving its lightweight simplicity and all existing functionality. No framework or heavy UI library will be introduced; the stack remains vanilla HTML/CSS/JS.

The app currently renders a navy sidebar with an audio lesson list, a main reader area with a native `<audio>` element, and two side-by-side `<pre>` panels for Latvian transcript and English translation. This modernization touches typography, spacing, color tokens, layout, dark mode, skeleton/loading states, empty states, audio waveform visualization, progress indicators, responsive behavior, and accessibility.

## Glossary

- **App**: The Latvian Listening Library single-page application at `latvian-listening-library/web/`.
- **Sidebar**: The left navigation panel containing the brand mark, search input, and collapsible lesson lists.
- **Reader**: The main content area to the right of the Sidebar, containing the Hero, Player Card, and Text Panels.
- **Hero**: The card at the top of the Reader showing the lesson title, subtitle, and status badge.
- **Player_Card**: The card in the Reader that contains the audio player and navigation buttons.
- **Audio_Player**: The UI component responsible for audio playback controls (play/pause, seek, volume).
- **Waveform_Visualizer**: The optional visual representation of audio amplitude over time, rendered from waveform JSON data when available.
- **Progress_Bar**: The simple seek/progress bar used as a fallback when waveform data is absent.
- **Text_Panel**: A card displaying either the Latvian transcript or the English translation for the selected lesson.
- **Skeleton_State**: A placeholder UI shown in place of content while data is loading.
- **Empty_State**: A UI shown when no lesson is selected or no search results are found.
- **Design_Token**: A named CSS custom property (variable) representing a spacing, color, radius, shadow, or typography value.
- **Dark_Mode**: A color scheme that uses dark backgrounds and light text, activated by system preference or manual toggle.
- **Theme_Toggle**: A UI control that allows the user to switch between light and dark color schemes.
- **Sticky_Player**: An Audio_Player that remains visible at the bottom of the viewport when the user scrolls on mobile.
- **Focus_Ring**: A visible outline applied to interactive elements when they receive keyboard focus.
- **Catalog**: The `catalog.json` file fetched by `app.js` that contains lesson metadata including audio URLs, transcripts, and status.
- **Lesson**: A single entry in the Catalog representing one audio file with its associated transcript and translation.
- **Status_Badge**: A pill-shaped label indicating the processing status of a Lesson (completed, transcribed only, failed, etc.).
- **Level_Section**: A collapsible group of Lessons within the Sidebar, grouped by proficiency level (A1 or A2).

---

## Requirements

### Requirement 1: Design Token System

**User Story:** As a developer, I want all visual values defined as CSS custom properties, so that I can apply consistent styling across the App and support theming without touching component styles.

#### Acceptance Criteria

1. THE App SHALL define Design_Tokens for spacing using a 4px base scale named `--space-1` (4px) through `--space-8` (32px), border-radius values, box-shadow levels, font sizes, line heights, and semantic colors in `:root` within `styles.css`.
2. THE App SHALL extend the existing CSS variable set rather than replacing it, preserving `--navy`, `--magenta`, `--paper`, `--ink`, `--muted`, `--line`, `--success`, `--warn`, and `--danger`.
3. THE App SHALL define semantic color tokens (`--color-surface`, `--color-surface-raised`, `--color-text-primary`, `--color-text-secondary`, `--color-accent`, `--color-border`) with light-theme values declared in `:root` and dark-theme values declared in both `@media (prefers-color-scheme: dark)` and `[data-theme="dark"]` selectors.
4. WHEN the `prefers-color-scheme: dark` media query matches, THE App SHALL remap all six semantic color tokens to dark-theme values so that any element using those tokens renders with the dark palette.
5. WHEN the `data-theme="dark"` attribute is present on the `<html>` element, THE App SHALL apply dark-theme token values, taking precedence over the system `prefers-color-scheme` setting.
6. WHEN the `data-theme="light"` attribute is present on the `<html>` element, THE App SHALL apply light-theme token values regardless of system preference.

---

### Requirement 2: Typography and Spacing Refresh

**User Story:** As a learner, I want clear typographic hierarchy and generous spacing, so that I can read transcripts and navigate lessons without visual strain.

#### Acceptance Criteria

1. THE App SHALL use a system font stack that prioritizes `-apple-system`, `BlinkMacSystemFont`, `"Segoe UI"`, `Roboto`, and `sans-serif` as the base body font.
2. THE App SHALL use a serif font stack (`Georgia`, `"Times New Roman"`, `serif`) exclusively for `.reading-text` content inside Text_Panels.
3. THE App SHALL set a minimum body font size of `1rem` (16px) and a line-height of at least `1.6` for body text.
4. THE App SHALL apply a modular type scale using Design_Tokens: `--text-xs` (0.75rem), `--text-sm` (0.875rem), `--text-base` (1rem), `--text-lg` (1.125rem), `--text-xl` (1.25rem), `--text-2xl` (1.5rem), `--text-3xl` (2rem).
5. THE App SHALL apply a minimum internal padding of `--space-4` (16px) to all cards — specifically the Hero, Player_Card, and Text_Panel — using Design_Tokens so that no card uses a hard-coded pixel value for internal spacing.
6. THE App SHALL set the gap between Sidebar lesson items to at least `--space-2` (8px) and the vertical gap between the Hero, Player_Card, and Text_Panel pair in the Reader to at least `--space-4` (16px).

---

### Requirement 3: Sidebar Layout and Navigation

**User Story:** As a learner, I want a well-organized sidebar with search and category browsing, so that I can quickly find the lesson I want to practice.

#### Acceptance Criteria

1. THE Sidebar SHALL display the brand mark, search input, and Level_Sections in a vertically stacked layout with spacing derived from the Design_Token spacing scale.
2. WHEN the user types in the search input, THE Sidebar SHALL update the visible lesson list within 300ms to show only Lessons whose title or filename contains the search query (case-insensitive).
3. THE Sidebar SHALL render each Level_Section as a collapsible group with a visible toggle button showing the section label and lesson count, expanded by default on page load.
4. WHEN a Level_Section toggle is activated, THE Sidebar SHALL expand or collapse the associated lesson list and update the `aria-expanded` attribute to `"true"` or `"false"` accordingly.
5. THE Sidebar SHALL display each Lesson as a button containing a triangular play indicator icon, the lesson title, and a status label.
6. WHEN a Lesson is selected, THE Sidebar SHALL apply a visually distinct active style to that Lesson's button using the `--color-accent` token as the background or left-border color.
7. THE Sidebar SHALL provide a search input with a visible `<label>` element and placeholder text.

---

### Requirement 4: Audio Player Modernization

**User Story:** As a learner, I want a clean, custom audio player, so that I can control playback comfortably on any device without relying on the browser's default controls.

#### Acceptance Criteria

1. THE Audio_Player SHALL replace the native `<audio controls>` element with a custom-styled player that provides play/pause, seek, current time, and duration controls.
2. THE Audio_Player SHALL expose ARIA labels on all interactive controls: play/pause button (`aria-label="Play"` / `aria-label="Pause"`), seek bar (`aria-label="Seek"`), and volume control if present.
3. WHEN audio is playing, THE Audio_Player SHALL update the Progress_Bar position at intervals of no more than 250ms to reflect the current playback position.
4. WHEN the user interacts with the Progress_Bar, THE Audio_Player SHALL seek to the corresponding position in the audio file.
5. IF waveform JSON data is available for the selected Lesson, THEN THE Waveform_Visualizer SHALL render the amplitude data as a visual bar or SVG path overlaid behind the Progress_Bar.
6. IF waveform JSON data is not available for the selected Lesson, THEN THE Audio_Player SHALL display the Progress_Bar without the Waveform_Visualizer and SHALL NOT block or delay audio playback.
7. THE Audio_Player SHALL display elapsed time and total duration in `mm:ss` format adjacent to the Progress_Bar.
8. WHEN the user is on a mobile viewport (width ≤ 768px) and the Player_Card has scrolled fully out of the viewport, THE Sticky_Player SHALL appear fixed at the bottom of the viewport with play/pause and progress controls visible; THE Sticky_Player SHALL be hidden when the Player_Card is visible in the viewport.
9. IF the audio source fails to load (network error or missing file), THEN THE Audio_Player SHALL display an inline error message and SHALL NOT leave the player in a broken or unresponsive state.

---

### Requirement 5: Transcript and Translation Panels

**User Story:** As a learner, I want clean, readable transcript and translation panels, so that I can follow along with the audio and understand the content.

#### Acceptance Criteria

1. THE Text_Panel SHALL render Latvian transcript and English translation content in a card with a visible heading, a divider, and body text that scrolls independently within the card when content overflows.
2. THE Text_Panel SHALL use the serif reading font at `--text-lg` size with a line-height of at least `1.72` for `.reading-text` content.
3. WHEN no Lesson is selected, THE Text_Panel SHALL display an Empty_State message: "Select an audio item to start listening."
4. WHEN a Lesson is selected and its transcript or translation is loading, THE Text_Panel SHALL display a Skeleton_State with animated placeholder lines.
5. WHEN a Lesson's transcript is unavailable, THE Text_Panel SHALL display the message "Latvian transcript is not available yet." using the `--color-text-secondary` token for text color.
6. WHEN a Lesson's translation is unavailable, THE Text_Panel SHALL display the message "English translation is not available yet." using the `--color-text-secondary` token for text color.
7. IF a Markdown source URL is available for the selected Lesson, THEN THE Text_Panel SHALL display a visible link to that URL.
8. IF no Markdown source URL is available for the selected Lesson, THEN THE Text_Panel SHALL hide the Markdown link element entirely.
9. IF the viewport width is greater than 900px, THEN THE Reader SHALL display the two Text_Panels side by side in a two-column grid.
10. IF the viewport width is 900px or less, THEN THE Reader SHALL stack the two Text_Panels vertically in a single column.

---

### Requirement 6: Empty States

**User Story:** As a learner, I want helpful empty states, so that I know what to do when no lesson is selected or no search results are found.

#### Acceptance Criteria

1. WHEN the App loads and no Lesson has been selected, THE Reader SHALL display an Empty_State in the Hero area with the heading "Select an audio item to start listening." and the supporting message "Choose a lesson from the sidebar to begin."
2. WHEN the App loads and no Lesson has been selected, THE Reader SHALL display a visible interactive element within the Hero Empty_State with the label "Try today's 5-minute challenge."
3. WHEN the App loads and no Lesson has been selected, THE Reader SHALL display a visible interactive element within the Hero Empty_State with the label "Browse by real-life situation."
4. WHEN the search input produces zero matching Lessons, THE Sidebar SHALL display an Empty_State message: "No lessons match your search. Try a different term."
5. WHEN the Catalog fails to load, THE Reader SHALL hide the Player_Card and both Text_Panels and SHALL display an error Empty_State with the message "Catalog not ready. Run the build script after processing audio."

---

### Requirement 7: Skeleton and Loading States

**User Story:** As a learner, I want skeleton placeholders while content loads, so that the interface feels responsive and I am not confused by blank areas.

#### Acceptance Criteria

1. WHEN the App is fetching the Catalog, THE Sidebar SHALL display Skeleton_State placeholders for at least three lesson items in each Level_Section; THE Sidebar SHALL replace the placeholders with real lesson buttons once the Catalog fetch completes.
2. WHEN a Lesson is selected and its transcript is being fetched or rendered, THE Text_Panel for the Latvian transcript SHALL display a Skeleton_State with three animated placeholder lines; THE Text_Panel SHALL replace the Skeleton_State with the transcript text once rendering is complete.
3. WHEN a Lesson is selected and its translation is being fetched or rendered, THE Text_Panel for the English translation SHALL display a Skeleton_State with three animated placeholder lines; THE Text_Panel SHALL replace the Skeleton_State with the translation text once rendering is complete.
4. THE Skeleton_State SHALL use a CSS `@keyframes` animation with a cycle duration between 1s and 2s that pulses opacity or shifts a gradient across placeholder lines to indicate loading activity; each placeholder line SHALL be at least 12px tall and at least 60% of the panel width.
5. WHEN `prefers-reduced-motion: reduce` matches, THE Skeleton_State animation SHALL be disabled and the placeholder SHALL be shown as a static block using the `--muted` color token.

---

### Requirement 8: Dark Mode

**User Story:** As a learner, I want the App to respect my system color scheme preference and allow me to override it, so that I can study comfortably in any lighting condition.

#### Acceptance Criteria

1. WHEN the system `prefers-color-scheme: dark` media query matches, THE App SHALL automatically apply the dark theme using remapped Design_Tokens without any user action.
2. THE App SHALL render a Theme_Toggle button in the Sidebar that allows the user to switch between light and dark themes.
3. WHEN the user activates the Theme_Toggle, THE App SHALL set `data-theme` on the `<html>` element to `"dark"` or `"light"` and persist the choice to `localStorage` under the key `"theme"`.
4. WHEN the App initializes, THE App SHALL read the `"theme"` key from `localStorage` and apply the stored theme before any page content is rendered.
5. IF no stored theme preference exists in `localStorage`, THEN THE App SHALL default to the system `prefers-color-scheme` value.
6. IF the current theme is light, THEN THE Theme_Toggle SHALL have `aria-label="Switch to dark mode"`.
7. IF the current theme is dark, THEN THE Theme_Toggle SHALL have `aria-label="Switch to light mode"`.
8. IF `localStorage` is unavailable (e.g., private browsing restrictions), THEN THE App SHALL fall back to the system `prefers-color-scheme` value and SHALL NOT throw an uncaught error.

---

### Requirement 9: Responsive Layout

**User Story:** As a learner, I want the App to work well on my phone, tablet, and desktop, so that I can practice listening wherever I am.

#### Acceptance Criteria

1. WHILE the viewport width is greater than 1200px, THE App SHALL display a two-column layout with the Sidebar at a fixed width between 300px and 390px and the Reader occupying the remaining flexible space, with the two Text_Panels rendered side by side.
2. WHILE the viewport width is between 769px and 1200px inclusive, THE App SHALL display the Sidebar and Reader side by side and SHALL stack the two Text_Panels vertically within the Reader.
3. WHILE the viewport width is 768px or less, THE App SHALL stack the Sidebar above the Reader in a single column; the Sidebar SHALL be collapsible and, when expanded, SHALL be constrained to a maximum height of `52vh` with internal scrolling.
4. WHILE the viewport width is 768px or less and a Lesson is playing, THE App SHALL display the Sticky_Player fixed at the bottom of the viewport.
5. THE App SHALL use `min-width` media queries as the primary responsive strategy, with a mobile-first baseline (default styles target the smallest viewport).
6. THE App SHALL ensure all interactive touch targets measure at least `44px × 44px` on viewports of 768px or less.
7. THE App SHALL not introduce horizontal scrolling at any viewport width from 320px to 2560px.

---

### Requirement 10: Accessibility

**User Story:** As a learner using assistive technology or keyboard navigation, I want the App to be fully operable, so that I can access all content and controls without a mouse.

#### Acceptance Criteria

1. THE App SHALL ensure all interactive elements (buttons, links, inputs, seek bar) have a visible Focus_Ring when focused via keyboard, with a minimum outline width of `2px` and a contrast ratio of at least 3:1 against the adjacent background color.
2. THE App SHALL ensure all text content meets WCAG 2.1 AA color contrast requirements: at least 4.5:1 for normal text and 3:1 for large text (18px+ or 14px+ bold).
3. THE App SHALL provide `aria-label` attributes on all icon-only buttons, including the Theme_Toggle, play/pause button, and Level_Section toggle.
4. THE App SHALL associate all form inputs with visible `<label>` elements using `for`/`id` pairing.
5. WHEN `prefers-reduced-motion: reduce` matches, THE App SHALL disable all CSS transitions and animations except state-indicating animations (such as loading spinners) that are essential to communicating application state.
6. THE App SHALL use semantic HTML elements: `<aside>` for the Sidebar, `<main>` for the Reader, `<article>` for Text_Panels, `<nav>` for the lesson menu, and `<section>` for logical groupings.
7. WHEN audio playback state changes (play, pause, or track end), THE Audio_Player SHALL announce the new state to screen readers via an `aria-live="polite"` region.
8. THE seek bar SHALL be operable via keyboard arrow keys, advancing or rewinding the audio by 1 second per keypress.

---

### Requirement 11: Progress Visualization

**User Story:** As a learner, I want to see my progress through the lesson library, so that I feel motivated and can track how much I have completed.

#### Acceptance Criteria

1. THE App SHALL track which Lessons have been completed and display a visual completion indicator (checkmark or filled dot) on each completed Lesson button in the Sidebar.
2. THE Hero SHALL display a progress bar and a text label showing the ratio of completed Lessons to total Lessons for the currently active level (e.g., "3 of 24 completed").
3. WHEN a Lesson's audio playback reaches at least 80% of its total duration, THE App SHALL mark that Lesson as completed.
4. THE App SHALL persist lesson completion state across page reloads using `localStorage` under the namespaced key `"lll_completed"`, storing a JSON object mapping lesson IDs to boolean completion status.
5. WHEN the completion state stored in `localStorage` is updated, THE Sidebar completion indicators and Hero progress bar SHALL update immediately to reflect the new state without requiring a page reload.
6. WHERE exam-relevant Lessons are identified in the Catalog (e.g., via an `exam` boolean field), THE Hero SHALL display a secondary indicator showing the percentage of exam-relevant Lessons completed, labeled as an app estimate (e.g., "Exam readiness: 45% (estimated)").

---

### Requirement 12: Component State Testing

**User Story:** As a developer, I want the major UI states to be verifiable, so that I can confirm the design works correctly across all conditions.

#### Acceptance Criteria

1. WHEN the App is loaded with an empty Catalog (zero items), THE Reader SHALL display the "no lesson selected" Empty_State with the heading "Select an audio item to start listening." and the Player_Card SHALL be in a disabled or hidden state.
2. WHEN a mock Catalog entry is provided and `selectItem(0)` is called programmatically, THE Hero SHALL display the lesson title, THE Audio_Player SHALL have a non-empty `src` attribute, and both Text_Panels SHALL display their respective content or unavailability messages.
3. WHEN the `catalog.json` fetch is intercepted and delayed by at least 500ms, THE Sidebar SHALL display Skeleton_State placeholders for lesson items and THE Reader SHALL not display stale or broken content during the delay.
4. WHEN `data-theme="dark"` is set on the `<html>` element before the App renders, THE App SHALL apply dark-theme Design_Token values to all visible surfaces and text elements.
5. WHERE axe-core or Playwright accessibility checks are available, THE App SHALL produce zero violations at the `critical` or `serious` impact level in each of the four states described in criteria 1–4.
6. WHERE Playwright E2E tooling is available, THE App SHALL pass a mobile viewport smoke test at 375×812px that confirms the Sticky_Player's bounding box is within the visible viewport area and is not hidden via CSS during active audio playback.
