<script setup lang="ts">
import Card from "../components/Card.vue";
</script>

<template>
  <h1>Attempts</h1>
  <p>
    Placeholder. Server-side attempt persistence is tracked as
    <strong>T-022</strong> and depends on the Postgres migration (T-021); once
    those land this route will list real attempts. For now the vanilla app
    still owns attempt history through localStorage.
  </p>

  <Card title="Today's behaviour">
    <p>
      No data is fetched here yet. Visit the
      <a href="/latvian-a2-exam-app/">classic app</a> to see your current
      attempts.
    </p>
  </Card>
</template>
