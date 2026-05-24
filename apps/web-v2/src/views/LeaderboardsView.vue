<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import Card from "../components/Card.vue";

// T-052 — Leaderboards view (weekly / friends / by-city).
//
// Calls the three endpoints in ``server_app/services/leaderboards.py``:
//   GET /api/leaderboards/weekly
//   GET /api/leaderboards/friends
//   GET /api/leaderboards/by-city?city=<name>
//
// The payload exposes only ``account_id``, ``display_name`` (already
// privacy-filtered by the server: see services/leaderboards.py
// ``_resolve_display_names``), ``xp`` and ``rank``. We render only those
// fields so the UI cannot accidentally leak PII even if the server is
// updated later.

type Scope = "weekly" | "friends" | "by-city";

interface Entry {
  rank: number;
  account_id: string;
  display_name: string;
  xp: number;
}

interface Viewer {
  rank: number | null;
  xp: number;
  on_board: boolean;
}

interface BoardPayload {
  scope: string;
  scope_key: string | null;
  as_of: string;
  ttl_seconds: number;
  entries: Entry[];
  viewer: Viewer;
}

const ENDPOINTS: Record<Scope, string> = {
  weekly: "/api/leaderboards/weekly",
  friends: "/api/leaderboards/friends",
  "by-city": "/api/leaderboards/by-city",
};

const SCOPE_LABELS: Record<Scope, string> = {
  weekly: "This week",
  friends: "Friends",
  "by-city": "By city",
};

const scope = ref<Scope>("weekly");
const city = ref<string>("");
const limit = ref<number>(20);
const loading = ref<boolean>(false);
const error = ref<string>("");
const payload = ref<BoardPayload | null>(null);

const viewerLabel = computed(() => {
  if (!payload.value) return "";
  const v = payload.value.viewer;
  if (v.on_board && v.rank !== null) {
    return `You are ranked #${v.rank} with ${v.xp} XP.`;
  }
  if (v.xp > 0) {
    return `You have ${v.xp} XP but are not in the top ${limit.value}.`;
  }
  return "Earn XP to appear on the leaderboard.";
});

const asOfLabel = computed(() => {
  if (!payload.value?.as_of) return "";
  try {
    return new Date(payload.value.as_of).toLocaleString();
  } catch {
    return payload.value.as_of;
  }
});

async function loadBoard() {
  if (scope.value === "by-city" && !city.value.trim()) {
    error.value = "Enter a city name to load the city leaderboard.";
    payload.value = null;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const url = new URL(ENDPOINTS[scope.value], window.location.origin);
    url.searchParams.set("limit", String(limit.value));
    if (scope.value === "by-city") {
      url.searchParams.set("city", city.value.trim());
    }
    const response = await fetch(url.pathname + url.search, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (response.status === 401) {
      error.value = "Sign in to view the leaderboard.";
      payload.value = null;
      return;
    }
    if (!response.ok) {
      error.value = `Failed to load leaderboard (HTTP ${response.status}).`;
      payload.value = null;
      return;
    }
    payload.value = (await response.json()) as BoardPayload;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    payload.value = null;
  } finally {
    loading.value = false;
  }
}

function selectScope(next: Scope) {
  scope.value = next;
  void loadBoard();
}

onMounted(() => {
  void loadBoard();
});
</script>

<template>
  <h1>Leaderboards</h1>
  <p>
    Compare your XP against learners in your city, your friend group, or
    everyone in the past week. Privacy: only your chosen display name
    appears on the board — never your email or full name.
    Source: <code>GET /api/leaderboards/*</code> (T-052).
  </p>

  <Card title="Choose a leaderboard">
    <div class="lb-tabs" role="tablist">
      <button
        v-for="entry in (Object.entries(SCOPE_LABELS) as [Scope, string][])"
        :key="entry[0]"
        type="button"
        class="lb-tab"
        :class="{ 'lb-tab--active': scope === entry[0] }"
        role="tab"
        :aria-selected="scope === entry[0]"
        @click="selectScope(entry[0])"
      >
        {{ entry[1] }}
      </button>
    </div>

    <form
      v-if="scope === 'by-city'"
      class="lb-city-form"
      @submit.prevent="loadBoard"
    >
      <label for="lb-city">City</label>
      <input
        id="lb-city"
        v-model="city"
        type="text"
        placeholder="e.g. Riga"
        autocomplete="address-level2"
      />
      <button type="submit">Load</button>
    </form>
  </Card>

  <Card v-if="loading" title="Loading">
    <p>Fetching the leaderboard…</p>
  </Card>

  <Card v-else-if="error" title="Cannot load leaderboard">
    <p>{{ error }}</p>
  </Card>

  <Card
    v-else-if="payload"
    :title="`${SCOPE_LABELS[scope]}${payload.scope_key ? ` — ${payload.scope_key}` : ''}`"
  >
    <p class="lb-viewer">{{ viewerLabel }}</p>

    <ol v-if="payload.entries.length" class="lb-list">
      <li
        v-for="entry in payload.entries"
        :key="entry.account_id"
        class="lb-row"
        :data-rank="entry.rank"
      >
        <span class="lb-rank">#{{ entry.rank }}</span>
        <span class="lb-name">{{ entry.display_name }}</span>
        <span class="lb-xp">{{ entry.xp.toLocaleString() }} XP</span>
      </li>
    </ol>
    <p v-else class="lb-empty">
      No learners on this board yet — be the first to earn XP!
    </p>

    <p class="lb-footer">As of {{ asOfLabel }} (cached up to {{ payload.ttl_seconds }}s).</p>
  </Card>
</template>

<style scoped>
.lb-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.lb-tab {
  appearance: none;
  border: 1px solid var(--color-border, #334155);
  background: transparent;
  color: inherit;
  padding: 6px 14px;
  border-radius: 999px;
  cursor: pointer;
  font-size: 0.9rem;
}
.lb-tab--active {
  background: var(--color-accent, #2ea043);
  border-color: var(--color-accent, #2ea043);
  color: #ffffff;
}
.lb-city-form {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 8px;
}
.lb-city-form input {
  flex: 1 1 200px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--color-border, #334155);
  color: inherit;
  border-radius: 6px;
}
.lb-city-form button {
  padding: 6px 14px;
  background: var(--color-accent, #2ea043);
  color: #ffffff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}
.lb-viewer {
  font-size: 0.9rem;
  color: var(--color-text-dim, #94a3b8);
  margin: 0 0 12px;
}
.lb-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 6px;
}
.lb-row {
  display: grid;
  grid-template-columns: 60px 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 6px;
}
.lb-row[data-rank="1"] {
  background: linear-gradient(90deg, rgba(212, 167, 44, 0.18), transparent);
}
.lb-row[data-rank="2"] {
  background: linear-gradient(90deg, rgba(148, 163, 184, 0.18), transparent);
}
.lb-row[data-rank="3"] {
  background: linear-gradient(90deg, rgba(205, 127, 50, 0.18), transparent);
}
.lb-rank {
  font-weight: 700;
  color: var(--color-text-dim, #94a3b8);
}
.lb-name {
  font-weight: 600;
}
.lb-xp {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.lb-empty {
  font-size: 0.9rem;
  color: var(--color-text-dim, #94a3b8);
  margin: 8px 0 0;
}
.lb-footer {
  margin: 16px 0 0;
  font-size: 0.75rem;
  color: var(--color-text-dim, #94a3b8);
}
</style>
