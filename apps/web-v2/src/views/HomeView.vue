<script setup lang="ts">
import Card from "../components/Card.vue";
import Button from "../components/Button.vue";
import { useRouter } from "vue-router";

const router = useRouter();

function goToReadiness() {
  router.push({ name: "readiness" });
}
</script>

<template>
  <h1>lvcodex v2 (preview)</h1>
  <p>
    You're on the Vue 3 + TypeScript shell. The classic vanilla app is still
    the default and remains untouched at
    <a href="/latvian-a2-exam-app/">/latvian-a2-exam-app/</a>. New surfaces will
    be migrated to this shell route-by-route per T-036.
  </p>

  <Card title="What lives here">
    <ul>
      <li><strong>/v2/</strong> &mdash; this home page</li>
      <li><strong>/v2/readiness</strong> &mdash; readiness dashboard (placeholder; T-030)</li>
      <li><strong>/v2/attempts</strong> &mdash; attempts list (placeholder; T-022)</li>
    </ul>
  </Card>

  <Card title="Status">
    <p>
      Scaffold only. No API calls are wired up yet &mdash; this exists so future
      feature work can land in Vue components without touching the vanilla
      <code>latvian-a2-exam-app/app.js</code>.
    </p>
    <Button variant="primary" @click="goToReadiness">Open readiness</Button>
  </Card>
</template>
