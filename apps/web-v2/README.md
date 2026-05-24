# apps/web-v2 &mdash; lvcodex Vue 3 + TypeScript scaffold

This is the **new** Single Page App for lvcodex, mounted at **`/v2/`** in
production. It runs alongside the existing vanilla app at
`/latvian-a2-exam-app/`, which remains the default until the v2 shell reaches
feature parity. Created by task **T-036** (refactor train, Train 3).

## Layout

```
apps/web-v2/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── src/
    ├── App.vue
    ├── main.ts
    ├── styles.css
    ├── components/
    │   ├── Button.vue
    │   ├── Card.vue
    │   └── Layout.vue
    ├── router/
    │   └── index.ts
    └── views/
        ├── HomeView.vue            # /v2/
        ├── ReadinessView.vue       # /v2/readiness   (T-030 placeholder)
        └── AttemptsView.vue        # /v2/attempts    (T-022 placeholder)
```

## Local development

Requires Node 20+.

```bash
cd apps/web-v2
npm install
npm run dev
```

Vite serves the dev build on <http://localhost:5174>. The dev server uses base
`/` so deep links work without the production `/v2/` prefix.

## Production build

From the repo root:

```bash
npm run build:v2
```

This is a thin wrapper around `cd apps/web-v2 && npm run build`. The
build emits `apps/web-v2/dist/` with `base: "/v2/"`, which is exactly what the
Python server expects.

The Python server (`server_app/core.py`, end-of-file `T-036` block) serves
`apps/web-v2/dist/` under `/v2/` if and only if `dist/index.html` exists. If
the directory is missing the server responds with a friendly 503 explaining
how to build it &mdash; the vanilla app is unaffected.

## Routing

Vue Router uses HTML5 history mode with base `/v2/`, so:

| URL                  | View              |
| -------------------- | ----------------- |
| `/v2/`               | `HomeView.vue`    |
| `/v2/readiness`      | `ReadinessView.vue` (placeholder for T-030) |
| `/v2/attempts`       | `AttemptsView.vue` (placeholder for T-022) |

Any unknown path under `/v2/*` redirects client-side to the home view. The
server-side static handler also performs a SPA fallback to `index.html` so
deep links survive a browser refresh.

## Why a separate `package.json`?

The root `package.json` carries the regression suite (`npm test`) and exists
since before the Vue work began. Keeping the v2 SPA in its own package keeps
its Vite/Vue/TypeScript devDependencies (>200 MB of `node_modules`) out of
the root install path. CI does **not** build the v2 SPA yet (out of scope for
T-036); the root `npm test` script continues to gate `develop` as before.

## Component library

`components/Button.vue`, `components/Card.vue`, and `components/Layout.vue`
are intentionally minimal &mdash; just enough to demonstrate `<script setup
lang="ts">` patterns and prop typing. A real design system (tokens, theme
switching, etc.) is a follow-up task.

## Conventions

- All components use `<script setup lang="ts">`.
- Strict TypeScript (`tsconfig.json` &rarr; `"strict": true`).
- Props typed with interfaces and `defineProps<Props>()`.
- No global state library yet (Pinia will land if/when a feature needs it).
- One stylesheet shared globally (`src/styles.css`); component-scoped styles
  use Vue SFC `<style scoped>`.

## Out of scope for T-036

- Adding `npm run build:v2` to CI (do this when the first real feature lands).
- Wiring the SPA to the real backend API.
- Authentication, billing, attempts logic.
- Tailwind, Pinia, i18n.

Those land in follow-up tasks (T-022, T-030, T-044, etc.).
