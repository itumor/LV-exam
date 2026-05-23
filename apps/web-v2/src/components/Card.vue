<script setup lang="ts">
interface Props {
  title?: string;
}

defineProps<Props>();
</script>

<template>
  <section class="card">
    <h3 v-if="title" class="card__title">{{ title }}</h3>
    <div class="card__body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.card {
  background: var(--color-surface, #1e293b);
  border: 1px solid var(--color-border, #334155);
  border-radius: var(--radius, 8px);
  padding: var(--space-4, 24px);
  margin-bottom: var(--space-3, 16px);
}

.card__title {
  margin: 0 0 var(--space-2, 8px) 0;
  color: var(--color-text, #f1f5f9);
  font-size: 1.125rem;
}

.card__body {
  color: var(--color-text-dim, #94a3b8);
}
</style>
