import { computed, ref } from 'vue'
import { callRpc } from '@/services/_factory'
import { hasOfferOptions } from '@/shared/ui/whatsappOffer.js'

const REQUIREMENTS_RPC = 'msuite_whatsapp.api.v1.app.crud.get_template_send_requirements'

/**
 * Loads what a WhatsApp template needs at send time (expiry, coupon, tap link).
 * Stale responses (user switched template mid-fetch) are ignored.
 * @param {Function} [fetcher] (template) => Promise<requirements>; defaults to the whitelisted RPC.
 * @returns {{requirements: Ref, loading: Ref<boolean>, error: Ref<string>, needsOffer: ComputedRef<boolean>,
 *   load: (template: string) => Promise<void>, retry: () => Promise<void>, reset: () => void}}
 */
export function useTemplateOfferRequirements(fetcher = (template) => callRpc(REQUIREMENTS_RPC, { template })) {
  const requirements = ref(null)
  const loading = ref(false)
  const error = ref('')
  let currentTemplate = ''
  let requestId = 0

  /** Clear everything (template deselected). */
  function reset() {
    requestId += 1
    currentTemplate = ''
    requirements.value = null
    loading.value = false
    error.value = ''
  }

  /**
   * Fetch requirements for `template`. Sets `error` on failure; never throws.
   * @param {string} template
   */
  async function load(template) {
    reset()
    if (!template) return
    currentTemplate = template
    const id = requestId
    loading.value = true
    try {
      const res = await fetcher(template)
      if (id === requestId) requirements.value = res?.message ?? res ?? null
    } catch (e) {
      if (id === requestId) error.value = e?.message || 'Could not check this template\'s offer options.'
    } finally {
      if (id === requestId) loading.value = false
    }
  }

  /** Re-run the last failed fetch. */
  const retry = () => load(currentTemplate)

  return { requirements, loading, error, needsOffer: computed(() => hasOfferOptions(requirements.value)), load, retry, reset }
}
