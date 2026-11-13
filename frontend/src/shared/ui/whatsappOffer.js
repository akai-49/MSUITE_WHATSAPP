/**
 * Pure helpers for WhatsApp offer options (expiry, coupon, tap target).
 *
 * The limits (coupon length) and the "does this template need X" flags come
 * from the backend `get_template_send_requirements` response, never from
 * constants in this file. The server stays authoritative; these checks only
 * give the user fast feedback.
 */

const HTTP_PROTOCOLS = ['http:', 'https:']

/**
 * Count characters the way a person does (an emoji is one, not two UTF-16 units).
 * @param {string} text
 * @returns {number}
 */
export function charLength(text) {
  return [...String(text ?? '')].length
}

const LOCAL_DATE_TIME_RE = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?$/

/**
 * Offset (ms) of `timeZone` from UTC at the instant `utcMs`.
 * @param {number} utcMs
 * @param {string} timeZone IANA zone name.
 * @returns {number}
 * @throws {RangeError} when the zone name is unknown.
 */
function zoneOffsetMs(utcMs, timeZone) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric',
    hour: 'numeric', minute: 'numeric', second: 'numeric',
  }).formatToParts(new Date(utcMs))
  const get = (type) => Number(parts.find((p) => p.type === type).value)
  const asUtc = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour'), get('minute'), get('second'))
  return asUtc - Math.floor(utcMs / 1000) * 1000
}

/**
 * Parse a "YYYY-MM-DD HH:mm[:ss]" or "YYYY-MM-DDTHH:mm[:ss]" wall-clock time.
 * With `timeZone` the wall-clock time is read in that zone (the Frappe site
 * zone, for values entered in the picker); without it, in the browser zone.
 * @param {string} localDateTime
 * @param {string} [timeZone] IANA zone name; unknown names fall back to the browser zone.
 * @returns {number|null} UNIX milliseconds, or null if invalid.
 */
export function offerExpiryToMs(localDateTime, timeZone) {
  const match = LOCAL_DATE_TIME_RE.exec(String(localDateTime ?? '').trim())
  if (!match) return null
  const [year, month, day, hour, minute, second] = match.slice(1).map((part) => Number(part ?? 0))
  const date = new Date(year, month - 1, day, hour, minute, second)
  // Reject roll-overs such as 31 Feb or 29 Feb in a non-leap year.
  if (date.getMonth() !== month - 1 || date.getDate() !== day) return null
  if (timeZone) {
    try {
      const wall = Date.UTC(year, month - 1, day, hour, minute, second)
      return wall - zoneOffsetMs(wall - zoneOffsetMs(wall, timeZone), timeZone)
    } catch {
      // Unknown zone name: use the browser zone below.
    }
  }
  return date.getTime()
}

/**
 * Validate offer values against what the template needs.
 * @param {object|null} requirements Output of `get_template_send_requirements`.
 * @param {{expiresAt?: string, couponCode?: string, tapUrl?: string, tapTitle?: string}} values
 * @param {number} [nowMs] Injectable clock for tests.
 * @param {string} [timeZone] Site IANA zone the picker value is expressed in.
 * @returns {Object<string,string>} Map of field key to message; empty when valid.
 */
export function validateOffer(requirements, values, nowMs = Date.now(), timeZone) {
  const errors = {}
  if (!requirements) return errors
  const v = values || {}
  const expiresAt = String(v.expiresAt ?? '').trim()
  const coupon = String(v.couponCode ?? '')
  const tapUrl = String(v.tapUrl ?? '').trim()
  const tapTitle = String(v.tapTitle ?? '').trim()

  if (requirements.needs_expiry || expiresAt) {
    const ms = offerExpiryToMs(expiresAt, timeZone)
    if (!expiresAt) errors.expiresAt = 'Offer end date and time is required for this template.'
    else if (!requirements.needs_expiry) errors.expiresAt = 'This template has no countdown, so it takes no offer end time.'
    else if (ms === null) errors.expiresAt = 'Enter a valid date and time.'
    else if (ms <= nowMs) errors.expiresAt = 'Offer end must be in the future.'
  }

  if (coupon !== '') {
    if (!requirements.needs_coupon) errors.couponCode = 'This template has no Copy Offer Code button.'
    else if (coupon.trim() === '') errors.couponCode = 'Coupon code cannot be blank.'
    else if (charLength(coupon) > requirements.coupon_max) {
      errors.couponCode = `Coupon code can be at most ${requirements.coupon_max} characters.`
    }
  } else if (requirements.needs_coupon && !requirements.coupon_prefill) {
    errors.couponCode = 'Coupon code is required for this template.'
  }

  if (tapUrl || tapTitle) {
    if (!requirements.supports_tap_target) errors.tapUrl = 'This template does not support a custom link.'
    else if (!tapUrl) errors.tapUrl = 'Enter the link, or clear the title.'
    else if (!tapTitle) errors.tapTitle = 'Enter a title for the link, or clear the link.'
    else if (!isHttpUrl(tapUrl)) errors.tapUrl = 'Link must start with http:// or https://.'
  }
  return errors
}

/**
 * @param {string} url
 * @returns {boolean} True when `url` parses and uses http or https.
 */
function isHttpUrl(url) {
  try {
    return HTTP_PROTOCOLS.includes(new URL(url).protocol)
  } catch {
    return false
  }
}

/** @returns {{expiresAt:string,couponCode:string,tapUrl:string,tapTitle:string}} Blank offer values. */
export function emptyOfferValues() {
  return { expiresAt: '', couponCode: '', tapUrl: '', tapTitle: '' }
}

/**
 * Rebuild offer values from untrusted storage (sessionStorage draft): only the four known
 * keys survive and only if they are strings, so a tampered or stale blob cannot inject shape.
 * @param {*} raw Parsed JSON from storage (anything).
 * @returns {{expiresAt:string,couponCode:string,tapUrl:string,tapTitle:string}}
 */
export function sanitizeOfferValues(raw) {
  const blank = emptyOfferValues()
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return blank
  for (const key of Object.keys(blank)) {
    if (typeof raw[key] === 'string') blank[key] = raw[key]
  }
  return blank
}

/**
 * @param {object|null} requirements Output of `get_template_send_requirements`.
 * @returns {boolean} True when the template needs any offer input (otherwise render nothing).
 */
export function hasOfferOptions(requirements) {
  return !!(requirements && (requirements.needs_expiry || requirements.needs_coupon || requirements.supports_tap_target))
}

/**
 * Map offer values to the Bulk WhatsApp Message fields. The expiry string is
 * passed through untouched (site time; the server converts it).
 * @param {object} values Offer values (see `emptyOfferValues`).
 * @param {{includeEmpty?: boolean}} [options] With `includeEmpty` blank fields are sent as null,
 *   so re-saving an existing draft clears values from a template the user switched away from.
 *   Without it, nothing is returned when no value is set (payload unchanged for plain templates).
 * @returns {Object<string,string|null>}
 */
export function buildOfferFields(values, { includeEmpty = false } = {}) {
  const v = { ...emptyOfferValues(), ...(values || {}) }
  const clean = (text) => String(text ?? '').trim() || null
  const fields = {
    offer_expires_at: clean(v.expiresAt)?.replace('T', ' ') ?? null,
    coupon_code: clean(v.couponCode),
    tap_target_url: clean(v.tapUrl),
    tap_target_title: clean(v.tapTitle),
  }
  if (includeEmpty) return fields
  return Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== null))
}

/**
 * Restore offer values from a saved Bulk WhatsApp Message (draft / duplicate).
 * @param {object|null} doc
 * @returns {{expiresAt:string,couponCode:string,tapUrl:string,tapTitle:string}}
 */
export function offerValuesFromDoc(doc) {
  return {
    expiresAt: doc?.offer_expires_at ? String(doc.offer_expires_at).slice(0, 19) : '',
    couponCode: doc?.coupon_code || '',
    tapUrl: doc?.tap_target_url || '',
    tapTitle: doc?.tap_target_title || '',
  }
}

/**
 * Offer extras for the inbox send / start_conversation call. The inbox API takes
 * the expiry as UNIX ms, so the site-time picker value is converted here with the site zone.
 * @param {object|null} requirements
 * @param {object} values
 * @param {string} [timeZone] Site IANA zone.
 * @returns {{limited_time_offer_expiry_ms?: number, coupon_code?: string, tap_target?: {url:string,title:string}}}
 *   Empty when the template needs nothing or nothing is entered.
 */
export function buildInboxOfferExtras(requirements, values, timeZone) {
  if (!hasOfferOptions(requirements)) return {}
  const v = { ...emptyOfferValues(), ...(values || {}) }
  const extras = {}
  const ms = requirements.needs_expiry ? offerExpiryToMs(v.expiresAt, timeZone) : null
  if (ms !== null) extras.limited_time_offer_expiry_ms = ms
  const coupon = String(v.couponCode ?? '').trim()
  if (requirements.needs_coupon && coupon) extras.coupon_code = coupon
  const url = String(v.tapUrl ?? '').trim()
  const title = String(v.tapTitle ?? '').trim()
  if (requirements.supports_tap_target && url && title) extras.tap_target = { url, title }
  return extras
}

/**
 * A scheduled blast must not start after the offer has ended.
 * @param {string} expiresAt Offer end (site time).
 * @param {string|null} scheduledTime Scheduled start (same zone), or empty for "send now".
 * @returns {string} Error message, or '' when fine / not comparable.
 */
export function validateOfferSchedule(expiresAt, scheduledTime) {
  const end = offerExpiryToMs(expiresAt)
  const start = offerExpiryToMs(scheduledTime)
  if (end === null || start === null) return ''
  return end <= start ? 'Offer end must be later than the scheduled send time.' : ''
}

/**
 * @returns {string|undefined} The Frappe site's IANA time zone from the page boot data, if present.
 */
export function getSiteTimeZone() {
  return (typeof window !== 'undefined' && window.frappeBootData?.timezone?.system) || undefined
}

/**
 * One-line review text for the offer values.
 * @param {object} values
 * @returns {string} e.g. "Ends 2030-06-15 10:30:00 · Code SAVE10 · Link: Shop"; '' when nothing is set.
 */
export function offerSummaryText(values) {
  const v = { ...emptyOfferValues(), ...(values || {}) }
  return [
    v.expiresAt && `Ends ${v.expiresAt}`,
    String(v.couponCode).trim() && `Code ${String(v.couponCode).trim()}`,
    String(v.tapTitle).trim() && `Link: ${String(v.tapTitle).trim()}`,
  ].filter(Boolean).join(' · ')
}
