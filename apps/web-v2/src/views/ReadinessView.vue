<script setup lang="ts">
import Card from "../components/Card.vue";
</script>

<template>
  <h1>Readiness dashboard</h1>
  <p>
    Placeholder. The full per-skill readiness view (9/15 logic, risk badges) is
    tracked as <strong>T-030</strong>; this route exists today purely to prove
    the SPA shell renders and deep links resolve through the <code>/v2/</code>
    static handler.
  </p>

  <Card title="Coming soon">
    <ul>
      <li>Per-skill readiness % (listening, reading, writing, speaking, vocabulary)</li>
      <li>9/15 pass-rule indicator per skill</li>
      <li>Risk badges (green / amber / red)</li>
      <li>Recommended next mission link</li>
    </ul>
  </Card>
</template>
