<!-- In Frappe CRM the animated Lemnia mark is not shown: this keeps LLoader's props so the copied
     pages work unchanged, and uses frappe-ui's spinner, as Frappe CRM does. -->
<template>
  <span class="crm-loader" :class="{ 'crm-loader--block': !inline }" role="status" :aria-label="label || 'Loading'">
    <LoadingIndicator :style="{ width: px + 'px', height: px + 'px' }" />
    <span v-if="label && !inline" class="crm-loader-label">{{ label }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { LoadingIndicator } from 'frappe-ui'

const props = defineProps({
  inline: { type: Boolean, default: false },
  size: { type: Number, default: 0 },
  label: { type: String, default: '' },
  onDark: { type: Boolean, default: false },
  styleOverride: { type: String, default: '' },
})

// Lemnia sized its mark 64/168px; a spinner reads right far smaller.
const px = computed(() => Math.min(props.size || (props.inline ? 16 : 24), 24))
</script>

<style scoped>
.crm-loader {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ink-gray-5);
}
.crm-loader--block {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 24px 0;
}
.crm-loader-label {
  font-size: 13px;
}
</style>
