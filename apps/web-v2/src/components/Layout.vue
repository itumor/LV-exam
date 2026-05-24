<script setup lang="ts">
import { RouterLink } from "vue-router";
import { useTenant } from "../composables/useTenant";

// T-044: read the resolved tenant from the shared reactive composable
// state. The composable boots in main.ts before app mount so by the time
// this component renders the tenant is either resolved or the bundled
// fallback is in place.
const tenant = useTenant();
</script>

<template>
  <div class="layout">
    <header class="layout__header">
      <div class="layout__brand">
        <img
          v-if="tenant.tenant?.logo_url"
          :src="tenant.tenant.logo_url"
          :alt="`${tenant.tenant.name} logo`"
          class="layout__brand-logo"
        />
        <strong>{{ tenant.tenant?.name || "lvcodex" }}</strong>
        <span class="layout__brand-suffix">v2</span>
      </div>
      <nav class="layout__nav" aria-label="Primary">
        <RouterLink to="/" class="layout__nav-link">Home</RouterLink>
        <RouterLink to="/readiness" class="layout__nav-link">Readiness</RouterLink>
        <RouterLink to="/attempts" class="layout__nav-link">Attempts</RouterLink>
        <RouterLink to="/tutor" class="layout__nav-link">Tutor</RouterLink>
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
        lvcodex v2 scaffold (T-036) &middot;
        <span v-if="tenant.tenant && tenant.tenant.id !== 'default'">
          white-labelled for <strong>{{ tenant.tenant.name }}</strong>
          (T-044) &middot;
        </span>
        vanilla app remains at
        <a href="/latvian-a2-exam-app/">/latvian-a2-exam-app/</a>.
        <template v-if="tenant.tenant?.support_email">
          &middot; Support:
          <a :href="`mailto:${tenant.tenant.support_email}`">{{ tenant.tenant.support_email }}</a>
        </template>
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
  align-items: center;
  gap: var(--space-2, 8px);
}

.layout__brand-logo {
  height: 24px;
  width: auto;
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
