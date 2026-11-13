<!-- Status / stage pill, kit 05+07.
     kind: a lifecycle status (live, scheduled, planned, Active, Running, Completed,
     Paused, Draft, Approved, Failed…) mapped to one of the five semantic --status-*
     tones — OR a pipeline stage (cold…ready) kept on its own --stage-* ramp.
     Case-insensitive, so a list's 'live' and a detail page's 'Active' both land right.
     Text is always carried for a11y. -->
<template>
  <span class="status-pill" :class="pillClass"><slot>{{ label || kind }}</slot></span>
</template>

<script setup>
import { computed } from 'vue'
// Lifecycle status → semantic tone. One map covers list kinds AND the detail-page
// statuses (Active/Running/Completed/Paused/Draft) that used to force a hand-rolled
// pill in each #status slot. Unknown kinds fall back to neutral, never throw.
const TONE = {
  // direct semantic tones
  success: 'success', warning: 'warning', danger: 'danger', neutral: 'neutral', info: 'info',

  // positive / running / active
  live: 'success', published: 'success', active: 'success', running: 'success', approved: 'success',
  sent: 'success', answered: 'success', connected: 'success', ready: 'success', called: 'success',
  created: 'success', valid: 'success',

  // informational / scheduled / syncing
  scheduled: 'info', syncing: 'info',

  // warning / paused / attention / medium priority
  paused: 'warning', pending: 'warning', 'in progress': 'warning', 'in-progress': 'warning',
  in_progress: 'warning', voicemail: 'warning', medium: 'warning',

  // negative / error / high priority
  failed: 'danger', rejected: 'danger', bounced: 'danger', error: 'danger', high: 'danger',
  urgent: 'danger', deprecated: 'danger', blocked: 'danger', throttled: 'danger', invalid: 'danger',
  dropped: 'danger',

  // neutral / planned / low priority
  planned: 'neutral', draft: 'neutral', completed: 'neutral', ended: 'neutral', archived: 'neutral',
  closed: 'neutral', idle: 'neutral', todo: 'neutral', low: 'neutral', dnc: 'neutral',
  'do not call': 'neutral', duplicate: 'neutral', 'no answer': 'neutral', 'no-answer': 'neutral',
}
// Pipeline stages stay their own visual system (the --stage-* ramp), untouched.
const STAGE = { cold:'stage-cold', aware:'stage-aware', interested:'stage-interested', considering:'stage-considering', 'high-intent':'stage-high-intent', ready:'stage-ready' }
const props = defineProps({
  kind: { type: String, required: true },
  label: { type: String, default: '' },
})
const pillClass = computed(() => {
  const k = String(props.kind || '').toLowerCase().trim()
  if (STAGE[k]) return STAGE[k]
  return `sp--${TONE[k] || 'neutral'}`
})
</script>

<style scoped>
.status-pill {
  display: inline-flex;
  align-items: center;
  font-size: var(--fs-2xs, 11px);
  font-weight: 600;
  padding: 3px 9px;
  border-radius: var(--radius-pill, 999px);
  white-space: nowrap;
  line-height: 1.2;
}
/* Tones from the canonical --status-* palette. Base sizing comes from .status-pill;
   these only set the tone colours. */
.sp--success { background: var(--status-success-bg); color: var(--status-success-text); }
.sp--warning { background: var(--status-warning-bg); color: var(--status-warning-text); }
.sp--danger  { background: var(--status-danger-bg);  color: var(--status-danger-text); }
.sp--neutral { background: var(--status-neutral-bg); color: var(--status-neutral-text); }
.sp--info    { background: var(--status-info-bg);    color: var(--status-info-text); }
</style>
