<!-- In Frappe CRM the Lemnia mascot is not shown: this keeps AivoAvatar's props so the copied
     pages work unchanged, and draws a plain icon in Frappe CRM's muted style instead. -->
<template>
  <span class="crm-avatar-icon" :style="{ width: size + 'px', height: size + 'px' }" aria-hidden="true">
    <FeatherIcon :name="thinking || pose === 'thinking' ? 'loader' : 'message-circle'" :style="iconStyle" />
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { FeatherIcon } from 'frappe-ui'

const props = defineProps({
  pose: { type: String, default: 'bust' },
  size: { type: Number, default: 24 },
  thinking: { type: Boolean, default: false },
  onDark: { type: Boolean, default: false },
})

const iconStyle = computed(() => {
  const px = Math.max(14, Math.round(props.size * 0.45))
  return { width: px + 'px', height: px + 'px' }
})
</script>

<style scoped>
.crm-avatar-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 999px;
  background: var(--surface-gray-2);
  color: var(--ink-gray-5);
}
</style>
