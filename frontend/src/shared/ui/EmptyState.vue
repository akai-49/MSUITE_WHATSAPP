<template>
  <!-- Plain variant (default) — inline "nothing here yet" for lists/cells. -->
  <div v-if="variant === 'plain'" class="empty-state" :class="[`empty-state--${tone}`, effectiveKind ? `empty-state--${effectiveKind}` : '']">
    <!-- Custom glyph wins (slot / icon prop); otherwise Aivo owns the empty
         surface — pose + size come from `kind` (see KIND_POSE / KIND_SIZE). -->
    <div v-if="$slots.icon || icon" class="empty-state-icon">
      <slot name="icon">
        <Icon :name="typeof icon === 'string' ? icon : 'info-circle'" :size="32" />
      </slot>
    </div>
    <div v-else-if="glyph && !icon" class="glyph" :class="effectiveKind">{{ glyph }}</div>
    <!-- subtle = compact inline cell: no mascot (one Aivo per viewport) -->
    <AivoAvatar v-else-if="tone !== 'subtle' && kindPose" :pose="kindPose" :size="kindSize" />
    <div class="empty-state-title">{{ title }}</div>
    <div v-if="resolvedDescription" class="empty-state-desc">{{ resolvedDescription }}</div>
    <div v-if="$slots.actions || $slots.default" class="empty-state-actions">
      <slot name="actions">
        <slot />
      </slot>
    </div>
  </div>

  <!-- Card variant — full-surface empty state for a whole page/section
       (setup / no-run / loading), previously GsEmptyState.vue. -->
  <div v-else class="empty-card" :class="`empty-card--${variant}`">
    <LLoader v-if="variant === 'loading' && !icon" />
    <div v-else-if="glyph" class="glyph" :class="effectiveKind">{{ glyph }}</div>
    <AivoAvatar v-else-if="!icon && kindPose" :pose="kindPose" :size="kindSize" class="empty-card-aivo" />
    <div v-else class="empty-card-icon">
      <Icon :name="resolvedIconName" :size="32" />
    </div>
    <h3 class="empty-card-title">{{ title }}</h3>
    <p v-if="resolvedDescription" class="empty-card-body">{{ resolvedDescription }}</p>
    <div v-if="$slots.actions || $slots.default" class="empty-card-actions">
      <slot name="actions">
        <slot />
      </slot>
    </div>
    <div v-if="$slots.checklist" class="empty-card-checklist">
      <slot name="checklist" />
    </div>
  </div>
</template>

<script setup>
/**
 * EmptyState — one component for every "nothing here yet" surface.
 *
 * `variant="plain"` (default): inline empty state for lists/cells/tables
 *   (Inbox without conversations, Connections page with zero accounts…).
 *   Slots: `icon` (custom glyph, defaults to an inbox SVG), `actions`.
 *
 * `variant="setup" | "no-run" | "loading"`: full-surface card empty state
 *   for a whole page/section, each with its own icon-tint treatment.
 *   Slots: `actions`, `checklist`.
 */
import { computed } from 'vue'
import Icon from '@/shared/icons/Icon.vue'
import AivoAvatar from './AivoAvatar.vue'
import LLoader from './LLoader.vue'

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  /** Alias for `description` — kept for GsEmptyState-style callers. */
  body: { type: String, default: '' },
  /** Visual weight for the `plain` variant — `subtle` for inline empty cells. */
  tone: { type: String, default: 'default' },
  /** `plain` variant: any truthy value forces the icon block to render
   *  even when no slot is provided (e.g. `icon="default"`).
   *  Other variants: overrides the variant's default Icon.vue name. */
  icon: { type: [Boolean, String], default: false },
  /** 'plain' | 'setup' | 'no-run' | 'loading' */
  variant: { type: String, default: 'plain' },
  /** Aivo kind — first-run | no-results | zero-is-good | not-configured.
   *  Picks pose AND size (size tracks usefulness). Defaults from `variant`. */
  kind: { type: String, default: '' },
})

// Pose + size per kind. first-run invites (waving, hero); not-configured names the
// blocker (sleeping); everything else is a calm small bust that stays out of the way.
const GLYPHS = { error: '⚠', 'no-permission': '🔒' }
const glyph = computed(() => GLYPHS[props.kind] || null)

const KIND_POSE = { 'first-run': 'waving', 'no-results': 'bust', 'zero-is-good': 'bust', 'not-configured': 'sleeping' }
const KIND_SIZE = { 'first-run': 190, 'no-results': 72, 'zero-is-good': 72, 'not-configured': 120 }
const VARIANT_KIND = { setup: 'not-configured', 'no-run': 'zero-is-good' }
const effectiveKind = computed(() => props.kind || VARIANT_KIND[props.variant] || 'no-results')
const kindPose = computed(() => {
  if (glyph.value) return null
  return KIND_POSE[effectiveKind.value] || 'bust'
})
const kindSize = computed(() => (props.tone === 'subtle' && !props.kind ? 48 : KIND_SIZE[effectiveKind.value] || 72))

const resolvedDescription = computed(() => props.description || props.body)

const VARIANT_ICONS = { setup: 'settings', 'no-run': 'refresh', loading: 'clock' }
const resolvedIconName = computed(() => {
  if (typeof props.icon === 'string' && props.icon) return props.icon
  return VARIANT_ICONS[props.variant] || 'info-circle'
})
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 8px;
  padding: 32px 24px;
  color: var(--text-secondary);
}
.empty-state--subtle { padding: 16px 12px; }

.empty-state-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  opacity: 0.7;
  margin-bottom: 4px;
}
.empty-state-title {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 0.875rem;
}
.empty-state-desc {
  font-size: 0.75rem;
  max-width: 320px;
  line-height: 1.45;
}
.empty-state-actions {
  margin-top: 6px;
  display: inline-flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
}
.empty-state--first-run { padding: 52px 24px 56px; }
.empty-state--first-run .empty-state-title { font-size: 1rem; }

.glyph { font-size: 26px; margin-bottom: 4px; }
.glyph.error { color: var(--warning); }
.glyph.no-permission { color: var(--text-tertiary); }

/* ── Card variant (setup / no-run / loading) ─────────────────────── */
.empty-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 64px 40px;
  background: var(--bg-surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}
.empty-card-aivo { margin-bottom: 14px; }
.empty-card--setup   .empty-card-icon { background: var(--brand-light); color: var(--brand-dark); }
.empty-card--no-run  .empty-card-icon { background: var(--warning-bg);  color: var(--warning); }
.empty-card--loading .empty-card-icon { background: var(--bg-sunken);   color: var(--text-tertiary); }

.empty-card-icon {
  width: 64px; height: 64px;
  border-radius: 16px;
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 20px;
}
.empty-card-title {
  font-size: 16px; font-weight: 600; margin: 0 0 8px;
  letter-spacing: -0.01em; color: var(--text-primary);
}
.empty-card-body {
  font-size: 13.5px; color: var(--text-secondary); line-height: 1.6;
  max-width: 440px; margin: 0 0 24px;
}
.empty-card-actions { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
.empty-card-checklist {
  margin-top: 24px; text-align: left; width: 100%; max-width: 400px;
  background: var(--bg-sunken); border-radius: var(--radius-md); padding: 16px 20px;
}
</style>
