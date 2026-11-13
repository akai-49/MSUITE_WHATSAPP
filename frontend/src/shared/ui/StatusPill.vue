<!--
  Tiny status badge. Colour-coded by state so the marketer can read
  the page state from across the room (designer-speak).

  Originally Campaign-only (Draft/Active/Completed/Cancelled). Promoted
  to `shared/` so CRM (Lead/Deal status), Inbox (conversation status)
  and any future module reuse the same pill instead of reinventing one
  per module — see FRONTEND_ARCHITECTURE_AUDIT.md §8/§12.

  The mapping below is intentionally broad: it groups every status
  string we know about across modules into 5 visual tones (draft /
  active / positive / negative / neutral), rather than hand-mapping
  every doctype's exact status vocabulary one-by-one.
-->
<template>
  <span class="pill" :class="cls">{{ displayStatus }}</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status:   { type: String, default: '' },
  fallback: { type: String, default: 'Draft' },
  // Bypasses the string-based map below when the caller already knows
  // the exact tone it wants (e.g. CampaignStatusBadge, which has its
  // own Draft/Active/Paused/Completed vocabulary).
  tone:     { type: String, default: '' },
})

// Tone groups — status strings from Campaign, Ads, Social, WhatsApp,
// CRM Lead/Deal, Conversation, and Email (Bulk Email Message / Email
// Template) all map onto one of six tones.
const TONE_MAP = {
  // active / in-progress
  active: 'is-active', scheduled: 'is-active', publishing: 'is-active',
  open: 'is-active', contacted: 'is-active',
  qualified: 'is-active', nurturing: 'is-active', 'proposal sent': 'is-active',
  negotiation: 'is-active', 'verbal commit': 'is-active',
  queued: 'is-active', 'in progress': 'is-active',

  // positive / terminal-good
  completed: 'is-completed', published: 'is-completed', resolved: 'is-completed',
  approved: 'is-completed', won: 'is-completed', converted: 'is-completed', sent: 'is-completed',
  opened: 'is-completed', clicked: 'is-completed',

  // negative / terminal-bad — "partially failed" gets its own tone
  // (below) since some of the batch DID succeed, unlike a full failure.
  cancelled: 'is-cancelled', failed: 'is-cancelled', lost: 'is-cancelled',
  rejected: 'is-cancelled', archived: 'is-cancelled', bounced: 'is-cancelled',
  unsubscribed: 'is-cancelled', disabled: 'is-cancelled',

  // paused / in review / on-hold — amber/yellow tone
  pending: 'is-paused', 'in review': 'is-paused', in_review: 'is-paused',
  paused: 'is-paused', 'partially failed': 'is-paused', 'reconnect required': 'is-paused',

  // neutral / not-started
  draft: 'is-draft', new: 'is-draft',
}

const displayStatus = computed(() => {
  const val = (props.status || props.fallback || '').trim()
  const lower = val.toLowerCase()
  if (lower === 'pending' || lower === 'in_review' || lower === 'in review') {
    return 'IN REVIEW'
  }
  return val
})

const cls = computed(() => {
  if (props.tone) return props.tone
  const s = (props.status || props.fallback || '').toLowerCase().trim()
  return TONE_MAP[s] || 'is-draft'
})
</script>

<style scoped>
.pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  white-space: nowrap;
}
/* Lemnia record-state palette: green = go, amber = hold, red = stop, grey = idle, blue = info */
.is-draft     { background: var(--status-neutral-bg); color: var(--status-neutral-text); }
.is-active    { background: var(--status-success-bg); color: var(--status-success-text); }
.is-completed { background: var(--status-info-bg);    color: var(--status-info-text); }
.is-cancelled { background: var(--status-danger-bg);  color: var(--status-danger-text); }
.is-paused    { background: var(--status-warning-bg); color: var(--status-warning-text); }
</style>
