<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<template>
  <div class="layout">
    <header class="layout__header">
      <div class="layout__brand">
        <strong>lvcodex</strong>
        <span class="layout__brand-suffix">v2</span>
      </div>
      <nav class="layout__nav" aria-label="Primary">
        <RouterLink to="/" class="layout__nav-link">Home</RouterLink>
        <RouterLink to="/readiness" class="layout__nav-link">Readiness</RouterLink>
        <RouterLink to="/attempts" class="layout__nav-link">Attempts</RouterLink>
        <a href="/latvian-a2-exam-app/" class="layout__nav-link layout__nav-link--external">
          Classic app
        </a>
      </nav>
    </header>
    <main class="layout__main">
      <slot />
    </main>
    <footer class="layout__footer">
      <small>
        lvcodex v2 scaffold (T-036) &middot; vanilla app remains at
        <a href="/latvian-a2-exam-app/">/latvian-a2-exam-app/</a>.
      </small>
    </footer>
  </div>
</template>

<style scoped>
.layout {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.layout__header {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3, 16px);
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3, 16px) var(--space-4, 24px);
  border-bottom: 1px solid var(--color-border, #334155);
}

.layout__brand {
  font-size: 1.125rem;
  display: flex;
  align-items: baseline;
  gap: var(--space-2, 8px);
}

.layout__brand-suffix {
  font-size: 0.75rem;
  color: var(--color-accent, #38bdf8);
  background: rgba(56, 189, 248, 0.12);
  padding: 2px 6px;
  border-radius: 999px;
}

.layout__nav {
  display: flex;
  gap: var(--space-3, 16px);
  flex-wrap: wrap;
}

.layout__nav-link {
  color: var(--color-text-dim, #94a3b8);
}

.layout__nav-link.router-link-active {
  color: var(--color-text, #f1f5f9);
  font-weight: 600;
}

.layout__nav-link--external::after {
  content: " \2197"; /* up-right arrow */
  font-size: 0.75em;
}

.layout__main {
  flex: 1;
  padding: var(--space-4, 24px);
  max-width: 960px;
  width: 100%;
  margin: 0 auto;
}

.layout__footer {
  border-top: 1px solid var(--color-border, #334155);
  padding: var(--space-3, 16px) var(--space-4, 24px);
  color: var(--color-text-dim, #94a3b8);
  text-align: center;
}
</style>
