<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import Card from "../components/Card.vue";

// T-042 — Tutor dashboard view.
//
// Calls ``GET /api/tutor/students`` (server side:
// ``server_app/services/tutor.py``) and renders one row per supervised
// student with their per-skill readiness badges. Each row links to the
// HTML report at ``/api/tutor/students/<id>/report`` which the tutor
// can open in a new tab or print.
//
// The route is locked behind the tutor scope (org plan_tier='tutor' +
// caller is owner / role='tutor'); a 401 means the visitor is signed
// out and a 403 means they are signed in but lack the tutor role.

type Badge = "green" | "yellow" | "red";

interface SkillSummary {
  avg_score: number | null;
  badge: Badge;
  predicted_pass: boolean;
  sample_size: number;
}

interface StudentRow {
  account_id: string;
  role: string;
  joined_at: string;
  readiness: {
    per_skill: Record<string, SkillSummary>;
    overall_pass_predicted: boolean;
    last_updated: string;
  };
}

interface TutorPayload {
  org: { id: string; name: string; plan_tier: string };
  students: StudentRow[];
  generated_at: string;
}

const SKILLS = ["listening", "reading", "writing", "speaking"] as const;
const SKILL_LABELS: Record<string, string> = {
  listening: "Listening",
  reading: "Reading",
  writing: "Writing",
  speaking: "Speaking",
};

const loading = ref<boolean>(true);
const error = ref<string>("");
const payload = ref<TutorPayload | null>(null);

const studentCount = computed(() => payload.value?.students.length ?? 0);

function skillSummary(student: StudentRow, skill: string): SkillSummary {
  return (
    student.readiness.per_skill[skill] || {
      avg_score: null,
      badge: "red",
      predicted_pass: false,
      sample_size: 0,
    }
  );
}

function badgeText(skill: SkillSummary): string {
  if (skill.sample_size === 0 || skill.avg_score === null) {
    return "—";
  }
  return skill.avg_score.toFixed(1);
}

function reportUrl(student: StudentRow): string {
  const orgId = payload.value?.org.id ?? "";
  return `/api/tutor/students/${encodeURIComponent(student.account_id)}/report?org_id=${encodeURIComponent(orgId)}`;
}

async function loadStudents() {
  loading.value = true;
  error.value = "";
  try {
    const response = await fetch("/api/tutor/students", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (response.status === 401) {
      error.value = "Sign in with your tutor account to view this dashboard.";
      payload.value = null;
      return;
    }
    if (response.status === 403) {
      error.value =
        "Your account does not have the tutor role for any organization.";
      payload.value = null;
      return;
    }
    if (!response.ok) {
      const detail = await response.text();
      error.value = `Failed to load students (HTTP ${response.status}). ${detail}`;
      payload.value = null;
      return;
    }
    payload.value = (await response.json()) as TutorPayload;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    payload.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void loadStudents();
});
</script>

<template>
  <h1>Tutor dashboard</h1>
  <p>
    Live readiness rollup for every learner on your tutor-plan
    organization. Source:
    <code>GET /api/tutor/students</code> (T-042). PII (emails, password
    hashes) is intentionally not exposed — only the redacted
    <code>account_id</code> and the per-skill scores are surfaced.
  </p>

  <Card v-if="loading" title="Loading">
    <p>Fetching your supervised cohort…</p>
  </Card>

  <Card v-else-if="error" title="Cannot load tutor dashboard">
    <p>{{ error }}</p>
  </Card>

  <Card
    v-else-if="payload"
    :title="`${payload.org.name} — ${studentCount} student(s)`"
  >
    <p class="tutor-subtitle">
      Plan tier: <strong>{{ payload.org.plan_tier }}</strong>. Click a
      student row to open their printable readiness report.
    </p>

    <table class="tutor-table" v-if="studentCount > 0">
      <thead>
        <tr>
          <th>Student (account id)</th>
          <th>Joined</th>
          <th v-for="skill in SKILLS" :key="skill">{{ SKILL_LABELS[skill] }}</th>
          <th>Overall</th>
          <th>Report</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="student in payload.students"
          :key="student.account_id"
          class="tutor-row"
        >
          <td class="tutor-id">
            <code>{{ student.account_id }}</code>
            <span class="tutor-role">{{ student.role }}</span>
          </td>
          <td>{{ student.joined_at?.slice(0, 10) ?? "—" }}</td>
          <td v-for="skill in SKILLS" :key="skill">
            <span
              class="tutor-badge"
              :class="`tutor-badge-${skillSummary(student, skill).badge}`"
              :title="`Sample size: ${skillSummary(student, skill).sample_size}`"
            >
              {{ badgeText(skillSummary(student, skill)) }}
            </span>
          </td>
          <td>
            <span
              class="tutor-overall"
              :class="
                student.readiness.overall_pass_predicted
                  ? 'tutor-overall-pass'
                  : 'tutor-overall-fail'
              "
            >
              {{
                student.readiness.overall_pass_predicted
                  ? "On track"
                  : "Not ready"
              }}
            </span>
          </td>
          <td>
            <a
              :href="reportUrl(student)"
              target="_blank"
              rel="noopener"
              class="tutor-report-link"
              >Open</a
            >
          </td>
        </tr>
      </tbody>
    </table>

    <p v-else>
      No students in this organization yet. Invite learners by issuing
      vouchers through the institutional admin console.
    </p>

    <p class="tutor-footer">
      Generated at
      <time :datetime="payload.generated_at">{{ payload.generated_at }}</time>
    </p>
  </Card>
</template>

<style scoped>
.tutor-subtitle {
  font-size: 0.85rem;
  color: var(--color-text-dim, #94a3b8);
  margin: 0 0 12px;
}
.tutor-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.tutor-table th,
.tutor-table td {
  border-bottom: 1px solid var(--color-border, #334155);
  padding: 6px 8px;
  text-align: left;
}
.tutor-table th {
  background: rgba(255, 255, 255, 0.04);
  font-weight: 600;
}
.tutor-id code {
  font-size: 0.75rem;
  background: rgba(255, 255, 255, 0.06);
  padding: 2px 4px;
  border-radius: 3px;
}
.tutor-role {
  display: inline-block;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-left: 6px;
  color: var(--color-text-dim, #94a3b8);
}
.tutor-badge {
  display: inline-block;
  min-width: 36px;
  text-align: center;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 700;
  font-size: 0.75rem;
}
.tutor-badge-green {
  background: #2ea043;
  color: #fff;
}
.tutor-badge-yellow {
  background: #d4a72c;
  color: #1f2328;
}
.tutor-badge-red {
  background: #da3633;
  color: #fff;
}
.tutor-overall {
  font-weight: 600;
  font-size: 0.8rem;
}
.tutor-overall-pass {
  color: #2ea043;
}
.tutor-overall-fail {
  color: #da3633;
}
.tutor-report-link {
  font-size: 0.8rem;
  color: var(--color-accent, #38bdf8);
}
.tutor-footer {
  margin-top: 12px;
  font-size: 0.75rem;
  color: var(--color-text-dim, #94a3b8);
}
</style>
