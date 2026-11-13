<!--
  Collapsible "advanced" block. Used for power-user options that 95%
  of marketers leave at the default — billing event, tracking
  parameters, custom disclaimers, etc. Closed by default so the main
  flow stays uncluttered.

  Props:
    title    — bold heading shown in the summary row
    hint     — small grey text next to the title (e.g. "current: Impressions")
    open     — start open if true (default false)
-->
<template>
  <details class="adv" :open="open">
    <summary class="head">
      <!-- SVG chevron — sharper than the legacy ▸ glyph; rotates on
           open via parent's [open] state. `currentColor` so it picks
           up `.title`'s color without a separate style. -->
      <svg class="chev" viewBox="0 0 12 12" aria-hidden="true">
        <path d="M3.5 4.5L6 7l2.5-2.5"
              stroke="currentColor" stroke-width="1.6"
              stroke-linecap="round" stroke-linejoin="round"
              fill="none" />
      </svg>
      <span class="title">{{ title }}</span>
      <span v-if="hint" class="hint">{{ hint }}</span>
    </summary>
    <div class="body">
      <slot />
    </div>
  </details>
</template>

<script setup>
defineProps({
  title: { type: String,  required: true },
  hint:  { type: String,  default: '' },
  open:  { type: Boolean, default: false },
})
</script>

<style scoped>
.adv {
  border: 1px solid var(--ink-100, var(--ink-100));
  border-radius: 10px;
  background: var(--bg-surface);
  transition: border-color .15s, box-shadow .15s;
}
.adv[open] {
  border-color: color-mix(in srgb, var(--ink-500, #64748b) 18%, var(--ink-100, var(--ink-100)));
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  cursor: pointer;
  list-style: none;
  user-select: none;
  transition: background .12s;
  border-radius: 10px;
}
.head::-webkit-details-marker { display: none; }
.adv[open] > .head {
  border-radius: 10px 10px 0 0;
  border-bottom: 1px solid var(--ink-100, var(--ink-100));
}

/* Chevron — flush left of the title, rotates 180° on open. SVG keeps
   strokes crisp at any zoom level. */
.chev {
  width: 14px; height: 14px;
  color: var(--ink-500, var(--ink-500));
  flex-shrink: 0;
  transition: transform .18s cubic-bezier(0.4, 0, 0.2, 1);
}
.adv[open] > .head .chev { transform: rotate(180deg); }

.head:hover { background: rgba(52, 65, 156, 0.03); }
.head:hover .chev { color: var(--brand-500); }

.title {
  font-size: 15px;
  font-weight: 700;
  color: var(--ink-900, var(--ink-900));
}
.hint {
  color: var(--ink-500, var(--ink-500));
  font-size: 12px;
  margin-left: auto;
}

/* Body — generous top padding to give the first field room from the
   header border, slightly tighter bottom since the parent Section's
   margin handles the gap to the next sibling. */
.body { padding: 18px 18px 18px; }
</style>
