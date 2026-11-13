<!--
  Lightweight confirm dialog.

  Replaces `window.confirm()` (browser-chrome dialog that looks foreign
  inside the SPA, ignores theme, and can't render multi-paragraph copy
  or a warning callout). Built as a controlled component — parent owns
  `open` and listens for `confirm` / `cancel` / optional `alt`.

  Props:
    open      — boolean, mounts the dialog
    title     — short heading
    message   — body copy (paragraph)
    note      — optional callout below the body (yellow strip)
    confirm   — label of the primary action ("Publish to Meta")
    cancel    — label of the dismiss button ("Cancel")
    alt       — optional third action button label ("Save") rendered after confirm
    tone      — 'primary' | 'success' | 'danger' — paints the primary
                button. Defaults to 'primary'.
    busy      — disables buttons while an async action runs.

  Emits:
    confirm  — user clicked the primary action
    cancel   — user clicked dismiss, hit ESC, or clicked the backdrop
    alt      — user clicked the alternate third action button

  Accessibility: when alt is set, initial focus goes to the alt button
  (so Enter never lands on a destructive Discard action); otherwise traps focus
  on the primary button when opened. Closes on ESC, restores focus to the
  previously-focused element on close.
-->
<template>
  <Teleport to="body">
    <Transition name="cd-fade">
      <div
        v-if="open"
        class="cd-overlay"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        @click.self="onCancel"
        @keydown.esc.stop="onCancel"
      >
        <div class="cd-card" @click.stop>
          <h2 :id="titleId" class="cd-title">{{ title }}</h2>
          <p v-if="message" class="cd-message">{{ message }}</p>

          <!-- Optional extra content (e.g. an "also delete on the
               platform" checkbox) — rendered between body and note. -->
          <slot />

          <div v-if="note" class="cd-note">
            <FeatherIcon name="alert-triangle" class="cd-note-icon w-4 h-4 flex-shrink-0" />
            <span>{{ note }}</span>
          </div>

          <div class="cd-actions">
            <button
              type="button"
              class="cd-btn cd-btn-secondary"
              :disabled="busy"
              @click="onCancel"
            >{{ cancel }}</button>
            <button
              ref="primaryBtn"
              type="button"
              class="cd-btn"
              :class="primaryClass"
              :disabled="busy"
              @click="onConfirm"
            >{{ busy ? busyLabel : confirm }}</button>
            <button
              v-if="alt"
              ref="altBtn"
              data-test="cd-alt"
              type="button"
              class="cd-btn cd-btn-primary"
              :disabled="busy"
              @click="onAlt"
            >{{ alt }}</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { FeatherIcon } from 'frappe-ui'

const props = defineProps({
  open:       { type: Boolean, default: false },
  title:      { type: String,  required: true },
  message:    { type: String,  default: '' },
  note:       { type: String,  default: '' },
  confirm:    { type: String,  default: 'Confirm' },
  cancel:     { type: String,  default: 'Cancel' },
  alt:        { type: String,  default: '' },
  tone:       { type: String,  default: 'primary' },
  busy:       { type: Boolean, default: false },
  busyLabel:  { type: String,  default: 'Working…' },
})
const emit = defineEmits(['confirm', 'cancel', 'alt'])

const titleId    = `cd-title-${Math.random().toString(36).slice(2, 9)}`
const primaryBtn = ref(null)
const altBtn     = ref(null)
let lastActive = null

watch(() => props.open, async (now) => {
  if (now) {
    // Save the focus so we can restore it on close — keeps screen-
    // reader users oriented.
    lastActive = document.activeElement
    await nextTick()
    if (props.alt) {
      altBtn.value?.focus()
    } else {
      primaryBtn.value?.focus()
    }
  } else if (lastActive && typeof lastActive.focus === 'function') {
    lastActive.focus()
  }
})

const primaryClass = computed(() => {
  switch (props.tone) {
    case 'success': return 'cd-btn-success'
    case 'danger':  return 'cd-btn-danger'
    default:        return 'cd-btn-primary'
  }
})

function onConfirm() { if (!props.busy) emit('confirm') }
function onCancel()  { if (!props.busy) emit('cancel') }
function onAlt()     { if (!props.busy) emit('alt') }
</script>

<style scoped>
.cd-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  /* Must outrank whatever it is confirming. Page modals sit at 2000
     (inbox, customer panel), so 1000 put the confirm *behind* the very
     dialog that raised it. This is the last thing the user has to answer,
     so it goes above every other layer. */
  z-index: 10000;
  padding: 20px;
}
.cd-card {
  background: var(--bg-surface);
  border-radius: 14px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.25), 0 0 0 1px rgba(15, 23, 42, 0.05);
  width: min(480px, 100%);
  padding: 24px 24px 20px;
  font-family: var(--font-stack, system-ui, -apple-system, sans-serif);
  color: var(--ink-900, var(--ink-900));
}
.cd-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.3;
}
.cd-message {
  margin: 0 0 14px;
  font-size: 14px;
  color: var(--ink-700, var(--ink-700));
  line-height: 1.55;
}
.cd-note {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  background: rgba(245, 158, 11, 0.10);
  border: 1px solid rgba(245, 158, 11, 0.32);
  color: var(--amber-800, #92400e);
  font-size: 12.5px;
  line-height: 1.5;
  padding: 10px 12px;
  border-radius: 10px;
  margin-bottom: 18px;
}
.cd-note-icon { font-size: 14px; line-height: 1; margin-top: 1px; }

.cd-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}
.cd-btn {
  height: 38px;
  padding: 0 16px;
  border-radius: 9px;
  font-weight: 600;
  font-size: 13.5px;
  cursor: pointer;
  border: 1.5px solid transparent;
  font-family: inherit;
  transition: background .12s, border-color .12s, color .12s, transform .06s;
}
.cd-btn:active:not(:disabled) { transform: translateY(1px); }
.cd-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.cd-btn-secondary {
  background: var(--bg-surface);
  border-color: var(--ink-200, var(--ink-200));
  color: var(--ink-700, var(--ink-700));
}
.cd-btn-secondary:hover:not(:disabled) {
  border-color: var(--ink-300, var(--ink-400));
  background: var(--ink-25, var(--ink-25));
}
.cd-btn-primary {
  background: var(--brand-500);
  color: white;
  border-color: var(--brand-500);
}
.cd-btn-primary:hover:not(:disabled) {
  background: var(--brand-600);
  border-color: var(--brand-600);
}
.cd-btn-success {
  background: var(--green-600, #16a34a);
  color: white;
  border-color: var(--green-600, #16a34a);
}
.cd-btn-success:hover:not(:disabled) {
  background: var(--green-700, #15803d);
  border-color: var(--green-700, #15803d);
}
.cd-btn-danger {
  background: var(--red-600, #dc2626);
  color: white;
  border-color: var(--red-600, #dc2626);
}
.cd-btn-danger:hover:not(:disabled) {
  background: var(--red-700, #b91c1c);
  border-color: var(--red-700, #b91c1c);
}

/* Fade-in transition — kept subtle so it doesn't compete with the
   editor's existing motion. */
.cd-fade-enter-active, .cd-fade-leave-active { transition: opacity .14s ease; }
.cd-fade-enter-from, .cd-fade-leave-to       { opacity: 0; }
.cd-fade-enter-active .cd-card,
.cd-fade-leave-active .cd-card {
  transition: transform .18s cubic-bezier(.2,.8,.2,1);
}
.cd-fade-enter-from .cd-card { transform: translateY(8px) scale(0.98); }
.cd-fade-leave-to .cd-card   { transform: translateY(4px) scale(0.99); }
</style>
