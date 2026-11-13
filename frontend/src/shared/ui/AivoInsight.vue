<!--
  AivoInsight.vue — Canonical AI recommendation and insight card.
  Renders with a dark surface, glowing accent, Aivo avatar, kicker, title,
  body slot, and optional #stats and #actions slots.
  Supports a dedicated `comingSoon` mode for upcoming AI capabilities.
-->
<template>
  <div class="lai" :class="{ 'lai--coming-soon': comingSoon }">
    <div class="lai__glow" />
    <div class="lai__head">
      <AivoAvatar pose="bust" :size="36" on-dark />
      <div class="lai__head-text">
        <div class="lai__kicker-row">
          <div class="lai__kicker">{{ resolvedKicker }}</div>
          <span v-if="comingSoon" class="lai__badge">Coming soon</span>
        </div>
        <div class="lai__who">{{ resolvedTitle }}</div>
      </div>
    </div>

    <p class="lai__body">
      <slot>
        <template v-if="comingSoon">
          AI-driven budget rebalancing and cross-channel optimization recommendations are coming soon. It will automatically identify underperforming campaigns and suggest high-yield shifts in real time.
        </template>
      </slot>
    </p>

    <div v-if="$slots.stats" class="lai__stats">
      <slot name="stats" />
    </div>

    <div v-if="$slots.actions || comingSoon" class="lai__foot">
      <slot name="actions">
        <button v-if="comingSoon" class="btn btn-ai-muted" disabled>
          Rebalance budget (Coming soon)
        </button>
      </slot>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import AivoAvatar from './AivoAvatar.vue'

/**
 * Props for AivoInsight.vue
 * @property {string} [kicker] - Sub-label above title (e.g. 'Aivo · budget move')
 * @property {string} [title] - Main headline of the insight
 * @property {boolean} [comingSoon] - Renders "Coming soon" badge and default empty state
 */
const props = defineProps({
  kicker: { type: String, default: '' },
  title: { type: String, default: '' },
  comingSoon: { type: Boolean, default: false },
})

const resolvedKicker = computed(() => {
  if (props.kicker) return props.kicker
  return props.comingSoon ? 'Campaign Intelligence' : 'Do this next'
})

const resolvedTitle = computed(() => {
  if (props.title) return props.title
  return props.comingSoon
    ? 'Automated budget shifts & insights'
    : 'Spend and leads recommendations'
})
</script>

<style scoped>
.lai {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: center;
  background: var(--ai-bg, #0b111e);
  border: 1px solid var(--ai-border, #1e293b);
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--shadow-sm);
  padding: 20px 22px;
  color: var(--ai-text, #f8fafc);
}
.lai__glow {
  position: absolute;
  top: -50px;
  right: -40px;
  width: 200px;
  height: 200px;
  background: radial-gradient(circle, rgba(45, 200, 182, 0.16), transparent 68%);
  pointer-events: none;
}
.lai__head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.lai__head-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.lai__kicker-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lai__kicker {
  font-size: var(--fs-2xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ai-label, #38bdf8);
}
.lai__badge {
  font-size: var(--fs-2xs);
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  border: 1px solid rgba(255, 255, 255, 0.15);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.lai__who {
  font-size: 14px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.01em;
}
.lai__body {
  font-size: 13.5px;
  line-height: 1.55;
  color: #e2e8f0;
  font-weight: 500;
  margin: 0;
}
.lai__body :deep(b) {
  color: #ffffff;
  font-weight: 700;
}
.lai__stats {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 14px 0 2px;
}
.lai__stats :deep(.lai-stat) {
  background: var(--ai-inset, rgba(15, 23, 42, 0.7));
  border: 1px solid var(--ai-border, #1e293b);
  border-radius: 10px;
  padding: 9px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
}
.lai__stats :deep(.lai-stat .dot) {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.lai__stats :deep(.lai-stat .amt) {
  margin-left: auto;
  font-weight: 800;
  color: #ffffff;
  font-variant-numeric: tabular-nums;
}
.lai__foot {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 15px;
  flex-wrap: wrap;
}
.btn-ai-muted {
  font-size: 12px;
  font-weight: 600;
  padding: 7px 14px;
  border-radius: var(--radius-pill, 999px);
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #94a3b8;
  cursor: not-allowed;
}
</style>
