<!--
  Generic KPI tile for dashboard top rows (Campaigns, Social, and any
  future module). `value === null` renders "—" instead of a fake
  number — used whenever a metric genuinely has no data yet (e.g.
  Cost-per-Lead with zero leads, or Social reach before any sync).

  Backwards compatible with Social and all existing callers.
  Supports step badges, fractional suffixes (e.g. / goal), progress bars,
  and delta indicators.
  Supports clickable buttons with keyboard focus, Enter/Space activation,
  aria-pressed toggling, and token-based active rings.
-->
<template>
  <component
    :is="clickable ? 'button' : 'div'"
    :type="clickable ? 'button' : undefined"
    class="kpi-card"
    :class="{
      'is-clickable': clickable,
      'is-active': active,
      'active': active,
      'has-step': Boolean(step)
    }"
    :aria-pressed="clickable ? (active ? 'true' : 'false') : undefined"
    @click="handleClick"
  >
    <span v-if="step" class="kpi-step">{{ step }}</span>
    <div class="kpi-label">
      <slot name="label">
        <Icon v-if="icon" :name="icon" :size="14" />
        {{ label }}
      </slot>
    </div>
    <div
      class="kpi-value"
      :style="valueColor ? { color: valueColor } : undefined"
    >
      <slot name="value">
        {{ value === null || value === undefined ? '—' : value }}
        <small v-if="small" class="kpi-small">{{ small }}</small>
      </slot>
    </div>
    <div v-if="bar !== null && bar !== undefined" class="kpi-bar">
      <i :style="{ width: Math.min(100, Math.max(0, bar)) + '%', background: barColor }" />
    </div>
    <div v-if="delta || $slots.delta" class="kpi-delta" :class="[deltaTone ? `tone-${deltaTone}` : '']">
      <slot name="delta">{{ delta }}</slot>
    </div>
    <div v-if="sub || $slots.sub" class="kpi-sub">
      <slot name="sub">{{ sub }}</slot>
    </div>
    <slot />
  </component>
</template>

<script setup>
import Icon from '@/shared/icons/Icon.vue'

/**
 * Props for KpiCard.
 * @property {string} label - Display label for metric
 * @property {string|number|null} [value] - Metric value or null for placeholder
 * @property {string} [small] - Inline small suffix next to value (e.g. / goal)
 * @property {string} [sub] - Secondary caption beneath value
 * @property {string} [icon] - Feather icon name
 * @property {string|number} [step] - Sequence step badge displayed in top-right
 * @property {number|null} [bar] - Progress bar percentage (0-100) or null to omit
 * @property {string} [barColor] - CSS color variable or hex for progress bar
 * @property {string} [delta] - Comparison text (e.g. '▲ 18% vs last month')
 * @property {string} [deltaTone] - Color tone: 'up', 'down', 'neutral'
 * @property {boolean} [clickable] - Whether to render as an interactive <button>
 * @property {boolean} [active] - Whether the card is selected/active (applies token ring and aria-pressed)
 * @property {string} [valueColor] - Custom CSS color token for the value
 */
const props = defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: null },
  small: { type: String, default: '' },
  sub: { type: String, default: '' },
  icon: { type: String, default: '' },
  step: { type: [String, Number], default: '' },
  bar: { type: Number, default: null },
  barColor: { type: String, default: 'var(--brand)' },
  delta: { type: String, default: '' },
  deltaTone: { type: String, default: '' },
  clickable: { type: Boolean, default: false },
  active: { type: Boolean, default: false },
  valueColor: { type: String, default: '' },
})

const emit = defineEmits(['click'])

function handleClick(event) {
  emit('click', event)
}
</script>

<style scoped>
.kpi-card {
  position: relative;
  display: block;
  width: 100%;
  padding: 16px 18px;
  background: var(--bg-surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md, 8px);
  text-align: left;
  box-sizing: border-box;
}
button.kpi-card,
.kpi-card.is-clickable {
  font-family: inherit;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  background: var(--bg-surface);
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background-color 0.15s ease;
}
button.kpi-card:hover,
.kpi-card.is-clickable:hover {
  border-color: var(--border-base, var(--border-color, #cbd5e1));
}
button.kpi-card:focus-visible,
.kpi-card.is-clickable:focus-visible {
  outline: none;
  border-color: var(--brand);
  box-shadow: 0 0 0 2px var(--bg-surface), 0 0 0 4px var(--brand);
}
.kpi-card.is-active,
.kpi-card.active {
  border-color: var(--brand);
  box-shadow: 0 0 0 1px var(--brand);
}
.kpi-card.is-active:focus-visible,
.kpi-card.active:focus-visible {
  box-shadow: 0 0 0 2px var(--bg-surface), 0 0 0 4px var(--brand);
}
.kpi-step {
  position: absolute;
  top: 12px;
  right: 13px;
  font-size: var(--fs-2xs, 11px);
  font-weight: 800;
  color: var(--text-tertiary);
}
.kpi-label {
  font-size: var(--fs-xs, 12px);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 9px;
}
.kpi-label :deep(svg) { color: var(--text-tertiary); }
/* L1 hero data: 26/800, tabular */
.kpi-value {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}
.kpi-small {
  font-size: var(--fs-xs, 12px);
  font-weight: 600;
  color: var(--text-tertiary);
  margin-left: 2px;
}
.kpi-bar {
  height: 4px;
  border-radius: 999px;
  background: var(--bg-sunken);
  overflow: hidden;
  margin: 8px 0 4px;
}
.kpi-bar i {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width 0.3s ease;
}
.kpi-delta {
  font-size: var(--fs-2xs, 11px);
  color: var(--text-secondary);
  margin-top: 6px;
  font-weight: 500;
}
.kpi-delta.tone-up {
  color: var(--success);
}
.kpi-delta.tone-down {
  color: var(--danger);
}
.kpi-sub {
  font-size: var(--fs-xs, 12px);
  color: var(--text-tertiary);
  margin-top: 5px;
}
</style>