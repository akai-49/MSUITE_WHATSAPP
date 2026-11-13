<!--
  AttributionBadge — how trustworthy a per-broadcast metric is.

  Shows "Exact" / "Template-level" / "Not available" with the rule as a
  tooltip (title) and an aria-label; focusable so keyboard and screen
  reader users get the same explanation.

  Props:
    level  — 'exact' | 'template_level' | 'unavailable' (unknown => unavailable)
    reason — optional server reason, appended to the rule
-->
<template>
  <span class="attr-badge" tabindex="0" :title="tip" :aria-label="`${meta.label}. ${tip}`">
    <StatusPill :status="meta.label" :tone="tone" />
  </span>
</template>

<script setup>
import { computed } from 'vue'
import StatusPill from '@/shared/ui/StatusPill.vue'
import { ATTRIBUTION_LEVELS } from './metricsFormat.js'

const props = defineProps({
  level: { type: String, default: 'unavailable' },
  reason: { type: String, default: '' },
})

const TONES = { exact: 'is-completed', template_level: 'is-paused', unavailable: 'is-draft' }

const meta = computed(() => ATTRIBUTION_LEVELS[props.level] || ATTRIBUTION_LEVELS.unavailable)
const tone = computed(() => TONES[props.level] || TONES.unavailable)
const tip = computed(() => (props.reason ? `${meta.value.rule} ${props.reason}` : meta.value.rule))
</script>

<style scoped>
.attr-badge { display: inline-flex; border-radius: 999px; }
.attr-badge:focus-visible { outline: 2px solid var(--brand, currentColor); outline-offset: 2px; }
</style>
