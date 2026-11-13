<!-- Shared shimmer loading placeholder. Extracted from Table.vue's
     skeleton (previously duplicated ad hoc across Campaigns.vue,
     WhatsAppTemplates.vue, etc.) so every loading state uses one
     shimmer visual that repaints correctly under the theme toggle. -->
<template>
  <div class="skel">
    <div
      v-for="i in lines"
      :key="i"
      class="skel-line"
      :style="{ height, width: i === lines ? lastLineWidth : '100%' }"
    />
  </div>
</template>

<script setup>
defineProps({
  lines: { type: Number, default: 1 },
  height: { type: String, default: '14px' },
  lastLineWidth: { type: String, default: '100%' },
})
</script>

<style scoped>
.skel-line {
  border-radius: 6px;
  margin-bottom: 10px;
  background: linear-gradient(90deg, var(--ink-50) 25%, var(--ink-100) 37%, var(--ink-50) 63%);
  background-size: 400% 100%;
  animation: skel-shimmer 1.4s ease infinite;
}
.skel-line:last-child { margin-bottom: 0; }
@keyframes skel-shimmer {
  0%   { background-position: 100% 50%; }
  100% { background-position: 0 50%; }
}
</style>
