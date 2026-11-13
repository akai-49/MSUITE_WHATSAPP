<!--
  Wizard stepper. Single-purpose: render the labelled pills, emit
  `select(index)` when clicked. The parent (AdComposer.vue) wires this
  into the store's `goToStep(target)` action which also enforces the
  "Brief must be saved before forward navigation" gate.
-->
<template>
  <nav class="stepper" aria-label="Composer steps">
    <div class="steps-list">
      <template v-for="(label, i) in steps" :key="i">
        <button
          type="button"
          class="step"
          :class="{
            'is-active': i === current,
            'is-done': isStepCompleted(i),
            'is-disabled': !isStepAccessible(i)
          }"
          @click="$emit('select', i)"
        >
          <span class="step-no">
            <template v-if="isStepCompleted(i)"><Icon name="check" :size="14" class="ei" /></template>
            <template v-else>{{ i + 1 }}</template>
          </span>
          <span>{{ label }}</span>
        </button>
        <span v-if="i < steps.length - 1" class="step-gap"></span>
      </template>
    </div>
    <div v-if="$slots.extra" class="stepper-extra">
      <slot name="extra" />
    </div>
  </nav>
</template>

<script setup>
const props = defineProps({
  steps:     { type: Array,  required: true },
  current:   { type: Number, required: true },
  completed: { type: Array,  default: () => [] },
})
defineEmits(['select'])

function isStepCompleted(index) {
  if (props.completed && props.completed.length > 0) {
    const allCompleted = props.completed.every(c => c)
    if (index === props.current && !allCompleted) {
      return false
    }
    for (let i = 0; i <= index; i++) {
      if (!props.completed[i]) return false
    }
    return true
  }
  if (index === props.current) {
    return false
  }
  return index < props.current
}

function isStepAccessible(index) {
  if (index <= 0) return true
  if (!props.completed || props.completed.length === 0) return true
  for (let i = 0; i < index; i++) {
    if (!props.completed[i]) return false
  }
  return true
}
</script>

<style scoped>
.stepper {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 4px 0 24px;
  border-bottom: 1px solid var(--ink-200);
}
.steps-list {
  display: flex;
  align-items: center;
  gap: 6px;
  /* flex-wrap: wrap; */
}
.stepper-extra {
  display: flex;
  align-items: center;
}
.step {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  border-radius: 999px;
  background: var(--ink-50);
  border: 1.5px solid var(--ink-100);
  color: var(--ink-500);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background .15s, color .15s, border-color .15s;
}
.step:hover:not(.is-active):not(.is-disabled) {
  background: var(--brand-50);
  color: var(--ink-900);
}
.step.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.step.is-done {
  color: var(--green-700);
  background: color-mix(in srgb, var(--green-500) 14%, transparent);
}
.step.is-active {
  color: var(--text-on-brand);
  background: var(--brand);
  border-color: var(--brand-500);
  font-weight: 600;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--brand-500) 35%, transparent);
}
.step-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.25);
  font-size: 11px;
  font-weight: 700;
}
.step:not(.is-active):not(.is-done) .step-no {
  background: var(--ink-300);
  color: var(--text-on-brand);
}
.step.is-done .step-no {
  background: var(--green-500);
  color: var(--text-on-brand);
}
.step-gap {
  flex: 0 0 12px;
  height: 2px;
  background: var(--ink-200);
  border-radius: 1px;
  align-self: center;
}
</style>
