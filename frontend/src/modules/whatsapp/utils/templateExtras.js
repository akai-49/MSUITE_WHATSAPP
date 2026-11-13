/**
 * Pure helpers for the template editor's `button_configuration` JSON blob.
 *
 * The blob is shared with other writers (template sync writes
 * `limited_time_offer`; older saves stored a bare array), so the editor must
 * merge its own keys into what is already stored instead of overwriting it.
 */
import { charLength } from '@/shared/ui/whatsappOffer.js'

const LTO_KEY = 'limited_time_offer'
const LTO_CATEGORY = 'MARKETING'
const LTO_HEADER_TYPES = ['IMAGE', 'VIDEO']

/**
 * Parse the stored blob into a plain object. Never throws.
 * @param {string|object|null|undefined} raw JSON text or an already parsed value.
 * @returns {object} The stored object; `{}` for empty, invalid, array or non-object input.
 */
function parseBlob(raw) {
  let value = raw
  if (typeof raw === 'string') {
    try {
      value = JSON.parse(raw)
    } catch {
      return {}
    }
  }
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

/**
 * Read the limited-time-offer settings out of a stored blob.
 * @param {string|object|null|undefined} raw
 * @returns {{enabled: boolean, text: string, hasExpiration: boolean}}
 */
export function parseLimitedTimeOffer(raw) {
  const lto = parseBlob(raw)[LTO_KEY]
  if (!lto || typeof lto !== 'object' || Array.isArray(lto)) {
    return { enabled: false, text: '', hasExpiration: false }
  }
  return {
    enabled: true,
    text: typeof lto.text === 'string' ? lto.text : '',
    hasExpiration: lto.has_expiration === true,
  }
}

/**
 * Build the JSON string saved in `button_configuration`, keeping every key the
 * editor does not own (including `limited_time_offer` written by template sync).
 *
 * @param {string|object|null|undefined} existingRaw Blob as loaded from the server.
 * @param {{buttons: Array, useLinkTracking: boolean, limitedTimeOffer?: ({text: string, hasExpiration: boolean}|null)}} next
 *   `limitedTimeOffer`: an object sets it, `null` removes it, omitted (undefined) leaves the stored value alone.
 * @returns {string} JSON text.
 */
export function mergeButtonConfiguration(existingRaw, { buttons, useLinkTracking, limitedTimeOffer }) {
  const merged = { ...parseBlob(existingRaw), buttons, use_link_tracking: useLinkTracking }
  if (limitedTimeOffer === null) {
    delete merged[LTO_KEY]
  } else if (limitedTimeOffer) {
    const previous = merged[LTO_KEY]
    merged[LTO_KEY] = {
      ...(previous && typeof previous === 'object' && !Array.isArray(previous) ? previous : {}),
      text: limitedTimeOffer.text.trim(),
      has_expiration: !!limitedTimeOffer.hasExpiration,
    }
  }
  return JSON.stringify(merged)
}

/**
 * Meta only allows limited-time-offer templates in the Marketing category with an image or video header.
 * @param {string} category
 * @param {string} headerType
 * @returns {boolean}
 */
export function isLimitedTimeOfferEligible(category, headerType) {
  return category === LTO_CATEGORY && LTO_HEADER_TYPES.includes(headerType)
}

/**
 * Validate the offer text.
 * @param {string} text
 * @param {number|null} max Character limit from the backend; null when unknown (server then decides).
 * @returns {string} Error message, or '' when valid.
 */
export function validateLimitedTimeOfferText(text, max) {
  if (!String(text ?? '').trim()) return 'Offer text is required.'
  if (max && charLength(text.trim()) > max) return `Offer text can be at most ${max} characters.`
  return ''
}
