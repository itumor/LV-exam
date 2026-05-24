<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import Card from "../components/Card.vue";

// T-030 — A2 readiness dashboard view.
//
// Calls ``GET /api/readiness`` (server side: server_app/services/readiness.py)
// and renders the four canonical A2 skills with per-skill bars, badges,
// and the 9/15 pass-threshold marker. Mirrors the vanilla-app tile in
// latvian-a2-exam-app/app.js so behaviour and visuals stay consistent
// while T-036 incrementally migrates surfaces to Vue 3.

interface SkillEntry {
  skill: string;
  avg_score: number | null;
  predicted_pass: boolean;
  badge: "green" | "yellow" | "red";
  sample_size: number;
}

interface ReadinessPayload {
  skills: SkillEntry[];
  overall_pass_predicted: boolean;
  last_updated: string;
}

const SKILL_LABELS: Record<string, string> = {
  listening: "Listening",
  reading: "Reading",
  writing: "Writing",
  speaking: "Speaking",
};
const MAX_POINTS = 15;
const PASS_THRESHOLD = 9;

const loading = ref<boolean>(true);
const error = ref<string>("");
const payload = ref<ReadinessPayload | null>(null);

const thresholdPercent = (PASS_THRESHOLD / MAX_POINTS) * 100;

const overallLabel = computed(() => {
  if (!payload.value) return "";
  return payload.value.overall_pass_predicted
    ? "On track to pass"
    : "Not yet predicted to pass";
});

const lastUpdatedLabel = computed(() => {
  if (!payload.value?.last_updated) return "—";
  try {
    return new Date(payload.value.last_updated).toLocaleString();
  } catch {
    return payload.value.last_updated;
  }
});

function skillLabel(skill: string): string {
  return SKILL_LABELS[skill] ?? skill;
}

function widthPercent(entry: SkillEntry): number {
  const raw = entry.avg_score ?? 0;
  return Math.max(0, Math.min(100, (raw / MAX_POINTS) * 100));
}

function scoreText(entry: SkillEntry): string {
  if (entry.sample_size === 0 || entry.avg_score === null) {
    return `— / ${MAX_POINTS}`;
  }
  return `${entry.avg_score.toFixed(1)} / ${MAX_POINTS}`;
}

function sampleText(entry: SkillEntry): string {
  return `${entry.sample_size} ${entry.sample_size === 1 ? "attempt" : "attempts"}`;
}

async function loadReadiness() {
  loading.value = true;
  error.value = "";
  try {
    const response = await fetch("/api/readiness", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (response.status === 401) {
      error.value = "Sign in to see your readiness dashboard.";
      payload.value = null;
      return;
    }
    if (!response.ok) {
      error.value = `Failed to load readiness (HTTP ${response.status}).`;
      payload.value = null;
      return;
    }
    payload.value = (await response.json()) as ReadinessPayload;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    payload.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void loadReadiness();
});
</script>

<template>
  <h1>Readiness dashboard</h1>
  <p>
    Per-skill predicted pass for the Latvian A2 naturalisation exam. Each row
    rolls up your last 10 attempts with newer attempts weighted higher;
    badges follow the 9/15-per-skill rule. Source:
    <code>GET /api/readiness</code> (T-030).
  </p>

  <Card v-if="loading" title="Loading">
    <p>Fetching your latest readiness rollup…</p>
  </Card>

  <Card v-else-if="error" title="Cannot load readiness">
    <p>{{ error }}</p>
    <p>
      <a href="/latvian-a2-exam-app/">Open the classic app</a> to sign in,
      then return here.
    </p>
  </Card>

  <Card v-else-if="payload" :title="`A2 readiness — ${overallLabel}`">
    <p class="readiness-subtitle">
      Badge legend:
      <span class="readiness-badge readiness-badge-green">GREEN</span> ≥ 12 / 15 ·
      <span class="readiness-badge readiness-badge-yellow">YELLOW</span> 9–11 / 15 ·
      <span class="readiness-badge readiness-badge-red">RED</span> &lt; 9 / 15
    </p>

    <ul class="readiness-list">
      <li
        v-for="entry in payload.skills"
        :key="entry.skill"
        class="readiness-row"
        :data-skill="entry.skill"
      >
        <div class="readiness-row-head">
          <span class="readiness-skill">{{ skillLabel(entry.skill) }}</span>
          <span
            class="readiness-badge"
            :class="`readiness-badge-${entry.badge}`"
            :title="`Risk: ${entry.badge}`"
          >
            {{ entry.badge.toUpperCase() }}
          </span>
        </div>
        <div
          class="readiness-bar"
          role="progressbar"
          :aria-valuemin="0"
          :aria-valuemax="MAX_POINTS"
          :aria-valuenow="entry.avg_score ?? 0"
          :aria-label="`${skillLabel(entry.skill)} readiness`"
        >
          <div
            class="readiness-bar-fill"
            :class="`readiness-bar-${entry.badge}`"
            :style="{ width: `${widthPercent(entry)}%` }"
          />
          <span
            class="readiness-threshold"
            :style="{ left: `${thresholdPercent}%` }"
            title="9/15 pass threshold"
          />
        </div>
        <div class="readiness-row-meta">
          <span>{{ scoreText(entry) }}</span>
          <span>{{ sampleText(entry) }}</span>
          <span class="readiness-predicted">
            {{ entry.predicted_pass ? "Predicted pass" : "Predicted fail" }}
          </span>
        </div>
      </li>
    </ul>

    <p class="readiness-footer">Last updated: {{ lastUpdatedLabel }}</p>
  </Card>
</template>

<style scoped>
.readiness-subtitle {
  font-size: 0.85rem;
  margin: 0 0 16px;
  color: var(--color-text-dim, #94a3b8);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.readiness-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 16px;
}
.readiness-row {
  display: grid;
  gap: 6px;
}
.readiness-row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.readiness-skill {
  font-weight: 600;
}
.readiness-badge {
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  padding: 3px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  color: #ffffff;
  white-space: nowrap;
}
.readiness-badge-green {
  background: #2ea043;
}
.readiness-badge-yellow {
  background: #d4a72c;
  color: #1f2328;
}
.readiness-badge-red {
  background: #da3633;
}
.readiness-bar {
  position: relative;
  height: 10px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  overflow: hidden;
}
.readiness-bar-fill {
  height: 100%;
  border-radius: 6px;
  transition: width 0.3s ease;
}
.readiness-bar-green {
  background: linear-gradient(90deg, #2ea043, #56d364);
}
.readiness-bar-yellow {
  background: linear-gradient(90deg, #d4a72c, #f0d96c);
}
.readiness-bar-red {
  background: linear-gradient(90deg, #da3633, #ff7b72);
}
.readiness-threshold {
  position: absolute;
  top: -2px;
  bottom: -2px;
  width: 2px;
  background: rgba(255, 255, 255, 0.65);
  pointer-events: none;
}
.readiness-row-meta {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 0.8rem;
  color: var(--color-text-dim, #94a3b8);
}
.readiness-predicted {
  font-weight: 600;
}
.readiness-footer {
  margin: 16px 0 0;
  font-size: 0.75rem;
  color: var(--color-text-dim, #94a3b8);
}
</style>
