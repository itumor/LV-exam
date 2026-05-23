<script setup lang="ts">
interface Props {
  variant?: "primary" | "secondary";
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
}

withDefaults(defineProps<Props>(), {
  variant: "primary",
  type: "button",
  disabled: false,
});

defineEmits<{ (e: "click", event: MouseEvent): void }>();
</script>

<template>
  <button
    :type="type"
    :disabled="disabled"
    :class="['btn', `btn--${variant}`]"
    @click="$emit('click', $event)"
  >
    <slot />
  </button>
</template>

<style scoped>
.btn {
  font: inherit;
  padding: 8px 16px;
  border-radius: var(--radius, 8px);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background-color 120ms ease, border-color 120ms ease;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn--primary {
  background: var(--color-accent, #38bdf8);
  color: #0f172a;
}

.btn--primary:hover:not(:disabled) {
  background: var(--color-accent-hover, #0ea5e9);
}

.btn--secondary {
  background: transparent;
  color: var(--color-text, #f1f5f9);
  border-color: var(--color-border, #334155);
}

.btn--secondary:hover:not(:disabled) {
  border-color: var(--color-accent, #38bdf8);
}
</style>
