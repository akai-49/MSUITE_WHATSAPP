<!-- src/shared/ui/ErrorState.vue
     Standard recoverable-failure state component.
     Never prints raw API paths or uncaught exception names to users.
     Technical error details are strictly sequestered into a collapsed
     <details> element displayed ONLY in DEV mode (import.meta.env.DEV). -->
<template>
  <div class="err-state" role="alert">
    <AivoAvatar pose="bust" :size="72" />
    <h2 class="err-title">{{ title || 'Something went wrong' }}</h2>
    <p v-if="processed.message" class="err-body">{{ processed.message }}</p>

    <!-- Technical details strictly restricted to DEV mode -->
    <details
      v-if="isDev && processed.technical"
      class="err-technical-details"
    >
      <summary class="err-technical-summary">Technical details</summary>
      <pre class="err-technical-pre">{{ processed.technical }}</pre>
    </details>

    <!-- Action slots / retry button -->
    <div v-if="$slots.default || hasRetry" class="err-actions">
      <slot>
        <button
          v-if="hasRetry"
          type="button"
          class="l-btn l-btn--secondary l-btn--sm err-retry-btn"
          @click="handleRetry"
        >
          <Icon name="refresh-cw" :size="13" />
          <span>Retry</span>
        </button>
      </slot>
    </div>
  </div>
</template>

<script>
/**
 * Sensitive patterns that should never be shown directly to end users.
 */
const TECHNICAL_PATTERNS = [
  /\/api\/method\//i,
  /\/api\/v\d+\//i,
  /\.py\b/,
  /\b(ValidationError|DoesNotExistError|PermissionError|AuthenticationError|TypeError|ReferenceError|SyntaxError|InternalServerError)\b/,
  /Traceback \(most recent call last\)/i,
  /\bHTTP\s*(?:4\d\d|5\d\d)\b/,
  /^\s*\{.*"exc_type"/s,
  /Cannot read propert(?:y|ies) of/i,
]

/**
 * Extracts a normalized string from string, Error, or response objects.
 * @param {*} raw - Raw error input
 * @returns {string} String representation
 */
function extractErrorString(raw) {
  if (!raw) return ''
  if (typeof raw === 'string') return raw.trim()
  if (raw instanceof Error) return raw.message || raw.toString()
  if (typeof raw === 'object') {
    if (raw.message && typeof raw.message === 'string') return raw.message.trim()
    if (raw.statusText) return raw.statusText
    try {
      return JSON.stringify(raw)
    } catch {
      return String(raw)
    }
  }
  return String(raw)
}
</script>

<script setup>
/**
 * ErrorState
 *
 * @component ErrorState
 * @description User-friendly, safe error boundary display. Prevents leaking backend stack traces or internal API paths.
 *
 * Props:
 * @prop {string} [title='Something went wrong'] - Heading text describing what failed.
 * @prop {string|object|Error} [message=''] - Primary error message.
 * @prop {Function} [retry=null] - Optional retry callback function.
 *
 * Attributes:
 * @attr {Function} [onRetry] - Optional retry listener (@retry="...").
 *
 * Side effects: None.
 */
import { computed, useAttrs } from 'vue'
import AivoAvatar from './AivoAvatar.vue'
import Icon from '@/shared/icons/Icon.vue'

const props = defineProps({
  title: {
    type: String,
    default: 'Something went wrong',
  },
  message: {
    type: [String, Object, Error],
    default: '',
  },
  retry: {
    type: Function,
    default: null,
  },
})

const attrs = useAttrs()
const isDev = Boolean(import.meta.env?.DEV)

/**
 * Process error text once into user-safe display message and optional technical details.
 */
const processed = computed(() => {
  const raw = extractErrorString(props.message)
  if (!raw) return { message: '', technical: '' }
  const isTechnical = TECHNICAL_PATTERNS.some((pattern) => pattern.test(raw))
  return {
    message: isTechnical ? 'Could not load this data. Try again.' : raw,
    technical: isTechnical ? raw : '',
  }
})

const hasRetry = computed(() => Boolean(props.retry || attrs.onRetry))

function handleRetry() {
  if (typeof props.retry === 'function') {
    props.retry()
  } else if (typeof attrs.onRetry === 'function') {
    attrs.onRetry()
  }
}
</script>

<style scoped>
.err-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 40px 24px;
  width: 100%;
  box-sizing: border-box;
}

.err-title {
  font-size: var(--fs-lg, 16px);
  font-weight: 600;
  margin: 16px 0 0;
  max-width: 480px;
  line-height: 1.35;
  color: var(--text-primary);
}

.err-body {
  font-size: var(--fs-sm, 13px);
  color: var(--text-secondary);
  margin: 8px 0 0;
  max-width: 420px;
  line-height: 1.5;
}

.err-technical-details {
  margin-top: 14px;
  max-width: 540px;
  width: 100%;
  text-align: left;
  background: var(--bg-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 6px);
  padding: 8px 12px;
  font-size: var(--fs-xs, 12px);
  color: var(--text-secondary);
}

.err-technical-summary {
  cursor: pointer;
  font-weight: 500;
  color: var(--text-primary);
  user-select: none;
}

.err-technical-pre {
  margin: 8px 0 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: var(--font-mono, monospace);
  font-size: var(--fs-2xs, 11px);
  color: var(--danger);
  max-height: 160px;
  overflow-y: auto;
}

.err-actions {
  margin-top: 20px;
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
}
</style>
