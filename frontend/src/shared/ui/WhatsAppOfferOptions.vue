<!--
  WhatsAppOfferOptions — the offer inputs a WhatsApp template needs at send time:
  one absolute offer end time, one coupon code, and an optional tap link.

  Shared by the broadcast wizard and the inbox template picker. It renders only
  what `requirements` (the `get_template_send_requirements` response) asks for;
  with nothing required it renders nothing. Validation lives in `whatsappOffer.js`
  (the parent calls `validateOffer` and passes the result as `errors`); the server
  stays authoritative.

  Props:
    requirements — { needs_expiry, needs_coupon, coupon_prefill, coupon_max, supports_tap_target }
    modelValue   — { expiresAt, couponCode, tapUrl, tapTitle } (expiresAt is "YYYY-MM-DD HH:mm:ss")
    errors       — map of field key to message, from validateOffer
    tone         — FormControl tone for every input ("sunken" inside grey-input dialogs)
  Emits:
    update:modelValue — the full values object with the changed field
-->
<template>
  <Section v-if="showExpiry || showCoupon || showTap" class="wa-offer" title="Offer options" hint="Filled in per send">
    <FormControl
      :tone="tone"
      v-if="showExpiry"
      type="datetime-local"
      label="Offer ends"
      :required="requirements.needs_expiry"
      :modelValue="values.expiresAt"
      :error="errors.expiresAt"
      hint="Shown to customers as a countdown."
      @update:modelValue="set('expiresAt', $event)"
    />
    <FormControl
      :tone="tone"
      v-if="showCoupon"
      type="text"
      label="Coupon code"
      :required="requirements.needs_coupon && !requirements.coupon_prefill"
      :modelValue="values.couponCode"
      :placeholder="requirements.coupon_prefill || ''"
      :error="errors.couponCode"
      :hint="couponHint"
      @update:modelValue="set('couponCode', $event)"
    />
    <AdvancedCollapse
      v-if="showTap"
      title="Custom link"
      hint="Optional"
      :open="!!(values.tapUrl || values.tapTitle || errors.tapUrl || errors.tapTitle)"
    >
      <div class="wa-offer-tap">
        <FormControl
      :tone="tone"
          type="url"
          label="Link"
          placeholder="https://"
          :modelValue="values.tapUrl"
          :error="errors.tapUrl"
          @update:modelValue="set('tapUrl', $event)"
        />
        <FormControl
      :tone="tone"
          type="text"
          label="Link title"
          :modelValue="values.tapTitle"
          :error="errors.tapTitle"
          @update:modelValue="set('tapTitle', $event)"
        />
      </div>
    </AdvancedCollapse>
  </Section>
</template>

<script setup>
import { computed } from 'vue'
import Section from '@/shared/ui/Section.vue'
import FormControl from '@/shared/ui/FormControl.vue'
import AdvancedCollapse from '@/shared/ui/AdvancedCollapse.vue'
import { charLength } from '@/shared/ui/whatsappOffer.js'

const props = defineProps({
  requirements: { type: Object, default: null },
  modelValue: { type: Object, default: () => ({}) },
  errors: { type: Object, default: () => ({}) },
  tone: { type: String, default: 'default' },
})
const emit = defineEmits(['update:modelValue'])

const values = computed(() => ({ expiresAt: '', couponCode: '', tapUrl: '', tapTitle: '', ...props.modelValue }))
const req = computed(() => props.requirements || {})

// A leftover value stays visible so its error ("no Copy button") can be seen and cleared.
const showExpiry = computed(() => !!req.value.needs_expiry || !!values.value.expiresAt)
const showCoupon = computed(() => !!req.value.needs_coupon || !!values.value.couponCode)
const showTap = computed(() => !!req.value.supports_tap_target || !!(values.value.tapUrl || values.value.tapTitle))

/**
 * Character counter and prefill note under the coupon input.
 * @returns {string}
 */
const couponHint = computed(() => {
  const max = req.value.coupon_max
  const count = max ? `${charLength(values.value.couponCode)} / ${max}` : ''
  return req.value.coupon_prefill ? `${count ? `${count}. ` : ''}Leave empty to use the template's saved code.` : count
})

/**
 * Emit the values object with one field changed.
 * @param {string} key
 * @param {string} value
 */
function set(key, value) {
  emit('update:modelValue', { ...values.value, [key]: value ?? '' })
}
</script>

<style scoped>
/* Sections default to a 32px bottom gap; offer options sit inside a larger form. */
.wa-offer { margin-bottom: 16px; min-width: 0; }
.wa-offer-tap { display: grid; gap: 16px; grid-template-columns: 1fr; }
/* Long coupon/URL text must wrap, not widen the 400px mobile layout. */
.wa-offer :deep(.err), .wa-offer :deep(.hint) { overflow-wrap: anywhere; }
@media (min-width: 640px) { .wa-offer-tap { grid-template-columns: 1fr 1fr; } }
</style>
