<!--
  Generic labelled form control. Wraps label + input + helper hint so
  every form field on every composer looks the same — same spacing,
  same focus ring, same hint colour, same "required" marker.

  Renders the right input element based on `type`:
    "text" | "tel" | "url" | "email" | "number"  → <input>
    "textarea"                                   → <textarea>
    "select"                                     → <select> with v-for options
    "date"                                       → frappe-ui <DatePicker>
    "datetime-local"                             → frappe-ui <DateTimePicker>

  We intentionally route every date/datetime through frappe-ui's pickers
  instead of the browser's native inputs. The native inputs render in
  the OS locale's clock convention (24-hour in many regions), which led
  to a real bug: a marketer would pick "11:50" reading it as AM, but
  the input had been showing 24-hour and the saved value was 23:50.
  frappe-ui's DateTimePicker forces a consistent 12-hour AM/PM picker
  and emits the backend's expected `YYYY-MM-DD HH:mm:ss` shape, so the
  whole stack speaks one date format.

  Value normalization (datetime-local):
    in : accepts either "YYYY-MM-DDTHH:mm[:ss]" or "YYYY-MM-DD HH:mm:ss"
    out: always emits "YYYY-MM-DD HH:mm:ss"

  Props:
    modelValue   — bound via v-model
    label        — text above the input
    type         — see above
    required     — adds the red asterisk to the label
    placeholder  — input placeholder
    hint         — small grey hint text below the input
    error        — red error text below the input (overrides hint)
    options      — for select type: [{ value, label }]
    rows         — for textarea: row count (default 3)
    maxlength    — character cap, surfaced as a small counter on the label
    list         — id of a <datalist> of suggestions (text inputs)
    defaultTime  — datetime-local: "HH:mm" for a newly picked day other than today
    min / max    — pass-through for number; mapped to minDateTime / maxDateTime
                   on date pickers (also accepts T-separator).
    disabled     — disabled state
    tone         — "default" (white input) or "sunken" (grey input, for dialogs
                   whose other inputs use the grey surface)
-->
<template>
  <div class="fc" :class="{ 'fc-sunken': tone === 'sunken' }">
    <label v-if="label && type !== 'checkbox'" class="lbl" :id="labelId" :for="isPicker ? null : inputId">
      {{ label }}
      <span v-if="required" class="req">*</span>
      <span v-if="maxlength && showCounter" class="counter">
        {{ (modelValue || '').length }} / {{ maxlength }}
      </span>
    </label>

    <div v-if="type === 'checkbox'" class="fc-checkbox-wrap">
      <label class="fc-checkbox-label" :for="inputId">
        <input
          type="checkbox"
          class="checkbox-input"
          :id="inputId"
          :disabled="disabled"
          :checked="isChecked"
          @change="onCheckboxChange"
          @blur="$emit('blur', $event)"
        />
        <span v-if="label" class="lbl-inline">
          {{ label }}
          <span v-if="required" class="req">*</span>
        </span>
      </label>
    </div>

    <select
      v-else-if="type === 'select'"
      class="input"
      :id="inputId"
      :disabled="disabled"
      :value="modelValue"
      @change="$emit('update:modelValue', $event.target.value)"
    >
      <!-- A required select can show its placeholder but not go back to it: picking
           "no value" left the form showing nothing while the old value stayed. -->
      <option v-if="placeholder" value="" :disabled="required">{{ placeholder }}</option>
      <option
        v-for="(o, i) in normalizedOptions"
        :key="`${o.value}-${i}`"
        :value="o.value"
        :disabled="o.disabled"
      >{{ o.label }}</option>
    </select>

    <textarea
      v-else-if="type === 'textarea'"
      class="input textarea"
      :id="inputId"
      :rows="rows"
      :maxlength="maxlengthAttr"
      :placeholder="placeholder"
      :disabled="disabled"
      :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)"
      @blur="$emit('blur', $event)"
      @change="$emit('change', $event)"
    ></textarea>

    <DateTimePicker
      v-else-if="type === 'datetime-local'"
      class="fc-picker"
      role="group"
      :aria-labelledby="label ? labelId : null"
      variant="outline"
      :modelValue="normalizedDateTime"
      :placeholder="placeholder || 'Pick a date and time'"
      :disabled="disabled"
      :clearable="true"
      :minDateTime="normalizedMin"
      :maxDateTime="normalizedMax"
      @update:modelValue="onDateTimeUpdate"
    />

    <DatePicker
      v-else-if="type === 'date'"
      class="fc-picker"
      role="group"
      :aria-labelledby="label ? labelId : null"
      variant="outline"
      :modelValue="modelValue || ''"
      :placeholder="placeholder || 'Pick a date'"
      :disabled="disabled"
      :clearable="true"
      @update:modelValue="$emit('update:modelValue', $event || '')"
    />

    <input
      v-else
      class="input"
      :id="inputId"
      :type="type"
      :maxlength="maxlengthAttr"
      :min="min || null"
      :max="max || null"
      :list="list || null"
      :placeholder="placeholder"
      :disabled="disabled"
      :value="modelValue"
      @input="$emit('update:modelValue', maybeNumber($event.target.value))"
      @blur="$emit('blur', $event)"
      @change="$emit('change', $event)"
    >

    <p v-if="error" class="err">{{ error }}</p>
    <p v-else-if="hint" class="hint">{{ hint }}</p>
  </div>
</template>

<script setup>
import { computed, useId } from 'vue'
import { DatePicker, DateTimePicker } from 'frappe-ui'

const props = defineProps({
  tone:        { type: String,  default: 'default', validator: (v) => ['default', 'sunken'].includes(v) },
  modelValue:  { type: [String, Number, Boolean], default: '' },
  label:       { type: String,  default: '' },
  type:        { type: String,  default: 'text' },
  required:    { type: Boolean, default: false },
  placeholder: { type: String,  default: '' },
  hint:        { type: String,  default: '' },
  error:       { type: String,  default: '' },
  list:        { type: String,  default: '' },
  // datetime-local: "HH:mm" given to a newly picked (non-today) day.
  defaultTime: { type: String,  default: '' },
  options:     { type: Array,   default: () => [] },
  rows:        { type: Number,  default: 3 },
  // `0` means "no limit" — bound conditionally below so we never emit
  // `maxlength="0"` to the DOM (which would lock the input to zero
  // characters). HTML doesn't have a "no maxlength" sentinel; the
  // attribute either exists with a positive integer or doesn't exist.
  maxlength:   { type: Number,  default: 0 },
  // Whether to show the character counter in the label when maxlength is set.
  showCounter: { type: Boolean, default: true },
  // Pass-through for date / datetime-local / number inputs. Empty
  // string maps to a missing attribute so callers can drop a `:min`
  // without polluting the DOM.
  min:         { type: [String, Number], default: '' },
  max:         { type: [String, Number], default: '' },
  disabled:    { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'blur', 'change'])

// Links the visible <label> to the control so screen readers and click-to-focus work.
const inputId = `fc-${useId()}`
// frappe-ui pickers expose no id for their inner input, so they are labelled through
// aria-labelledby on the picker wrapper instead of <label for>.
const labelId = `${inputId}-label`
const isPicker = computed(() => props.type === 'date' || props.type === 'datetime-local')

function onDateTimeUpdate(value) {
  if (!value) {
    emit('update:modelValue', '')
    return
  }

  const nextParts = String(value).split(' ')
  const nextDate = nextParts[0]
  const nextTime = nextParts[1] || ''

  const prevParts = String(props.modelValue || '').split(' ')
  const prevDate = prevParts[0]

  if (nextDate !== prevDate && nextTime === '00:00:00') {
    // A freshly picked day: `defaultTime` when one is set and the day is not
    // today (today keeps "now", so it never lands before a min of now);
    // otherwise the current time. Never with seconds.
    const now = new Date()
    const pad = (n) => String(n).padStart(2, '0')
    const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    const timeStr = props.defaultTime && nextDate !== today
      ? `${props.defaultTime}:00`
      : `${pad(now.getHours())}:${pad(now.getMinutes())}:00`
    emit('update:modelValue', `${nextDate} ${timeStr}`)
  } else {
    emit('update:modelValue', value)
  }
}

const maxlengthAttr = computed(() =>
  props.maxlength > 0 ? props.maxlength : null
)

// `YYYY-MM-DDTHH:mm[:ss]` (browser-native input shape) → space-separated
// canonical shape that frappe-ui and the backend both expect. Idempotent
// for already-canonical values so passing a backend payload straight
// through doesn't double-translate.
function _toCanonical(raw) {
  if (!raw) return ''
  const s = String(raw).trim()
  if (!s) return ''
  // Swap T-separator → space; pad seconds if the legacy
  // datetime-local input dropped them (`YYYY-MM-DDTHH:mm`).
  const swapped = s.includes('T') ? s.replace('T', ' ') : s
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(swapped)) return `${swapped}:00`
  return swapped
}

const normalizedDateTime = computed(() => _toCanonical(props.modelValue))
const normalizedMin      = computed(() => _toCanonical(props.min))
const normalizedMax      = computed(() => _toCanonical(props.max))

// Tolerate callers that pass either a flat string array
// (`['Image', 'Video']`) or the full object form
// (`[{value: 'image', label: 'Image'}]`). Picking ONE shape per
// callsite drifts inconsistently — normalising at the boundary lets
// both work and keeps the component honest.
const normalizedOptions = computed(() =>
  (props.options || []).map((o) => {
    if (o && typeof o === 'object') {
      const value = o.value ?? o.label ?? ''
      return { value, label: o.label ?? value, disabled: !!o.disabled }
    }
    return { value: o, label: String(o), disabled: false }
  }),
)

// `type="number"` is the trickiest — DOM gives us a string. We coerce
// only for number inputs, so `<FormControl type="number">` round-trips
// numeric state cleanly; other types stay as strings.
function maybeNumber(v) {
  if (props.type !== 'number') return v
  if (v === '' || v === null || v === undefined) return 0
  const n = parseFloat(v)
  return Number.isFinite(n) ? n : 0
}

const isChecked = computed(() => {
  if (typeof props.modelValue === 'boolean') return props.modelValue
  if (typeof props.modelValue === 'number') return props.modelValue === 1
  return Boolean(props.modelValue && props.modelValue !== '0' && props.modelValue !== 'false')
})

function onCheckboxChange(e) {
  const checked = e.target.checked
  const nextVal = typeof props.modelValue === 'number' ? (checked ? 1 : 0) : checked
  emit('update:modelValue', nextVal)
  emit('change', e)
}
</script>

<style scoped>
/* No sibling-based vertical spacing — parents manage it via flex
   `gap` or grid `gap`. The old `.fc + .fc { margin-top: 16px }` rule
   pushed every-but-the-first FormControl down within its slot, which
   in a 2-column grid like Schedule / UTM made the right-side fields
   sit lower than the left ones. */

.fc-checkbox-wrap {
  display: flex;
  align-items: center;
  min-height: 24px;
}
.fc-checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}
.fc-checkbox-label:has(:disabled) {
  cursor: not-allowed;
  opacity: 0.65;
}
.checkbox-input {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  border: 1.5px solid var(--ink-200);
  accent-color: var(--brand-500);
  cursor: pointer;
}
.checkbox-input:disabled {
  cursor: not-allowed;
}
.lbl-inline {
  font-weight: 500;
  font-size: 14px;
  color: var(--ink-900);
}

.lbl {
  display: block;
  margin: 0 0 8px;
  font-weight: 600;
  font-size: 14px;
  color: var(--ink-900, var(--ink-900));
  letter-spacing: 0.01em;
}
.req { color: var(--red-500, #dc2626); margin-left: 2px; }
.counter {
  float: right;
  font-weight: 400;
  font-size: 12px;
  color: var(--ink-500, var(--ink-500));
}

.input {
  width: 100%;
  height: 42px;
  padding: 10px 14px;
  border: 1.5px solid var(--ink-100, var(--ink-100));
  border-radius: 10px;
  background: var(--bg-surface);
  color: var(--ink-900, var(--ink-900));
  font-size: 15px;
  line-height: 1.4;
  box-sizing: border-box;
  transition: border-color .15s, box-shadow .15s;
}
.input.textarea { height: auto; min-height: 80px; resize: vertical; padding-top: 10px; }
.input:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--brand-500) 30%, var(--ink-100, var(--ink-100)));
}
.input:focus {
  outline: none;
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(52, 65, 156, 0.18);
}
.input:disabled {
  background: var(--ink-50, var(--ink-50));
  opacity: 0.65;
  cursor: not-allowed;
}

/* Custom select chevron — replaces the OS-default triangle */
select.input {
  -webkit-appearance: none;
  -moz-appearance: none;
  appearance: none;
  padding-right: 38px;
  background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8' fill='none'%3E%3Cpath d='M1 1.5L6 6.5L11 1.5' stroke='%23737373' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 14px center;
}

/* frappe-ui DatePicker / DateTimePicker — match the visual rhythm of
   our other inputs. The picker itself renders a TextInput wrapped in a
   Popover; we just need to make the wrapper full-width and our height. */
.fc-picker {
  width: 100%;
  display: block;
}
.fc-picker :deep(input) {
  height: 42px;
  font-size: 15px;
  border-radius: 10px;
  border: 1.5px solid var(--ink-100, var(--ink-100));
  background: var(--bg-surface);
}
.fc-picker :deep(input:hover:not(:disabled)) {
  border-color: color-mix(in srgb, var(--brand-500) 30%, var(--ink-100, var(--ink-100)));
}
.fc-picker :deep(input:focus) {
  outline: none;
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(52, 65, 156, 0.18);
}

/* Grey tone: match dialogs whose other inputs sit on --bg-sunken. */
.fc-sunken .input,
.fc-sunken .fc-picker :deep(input) { background: var(--bg-sunken); }

.hint {
  color: var(--ink-500, var(--ink-500));
  font-size: 12px;
  margin: 6px 0 0;
  line-height: 1.5;
}
.err {
  color: var(--red-700, #b91c1c);
  font-size: 12px;
  margin: 6px 0 0;
  line-height: 1.5;
}
</style>
