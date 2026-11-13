/**
 * Shared formatting for WhatsApp Marketing Messages metrics.
 *
 * Rule: a missing value (null/undefined/NaN) is "n/a", never 0.
 */

export const NOT_AVAILABLE = 'n/a'
export const CONVERSIONS_HINT = 'Needs Meta Pixel / Conversions API'
export const NO_CONVERSIONS_HINT = 'No conversions in this period'

/** Known send-route keys -> display label; anything else is humanized. */
const ROUTE_LABELS = {
  cloud_api: 'Cloud API',
  marketing_messages: 'Marketing Messages',
  unknown: 'Unknown route',
}

/** Attribution level -> badge label and one-sentence rule (tooltip). */
export const ATTRIBUTION_LEVELS = {
  exact: {
    label: 'Exact',
    rule: "Meta's daily numbers match this broadcast's own sends, so they belong to it alone.",
  },
  template_level: {
    label: 'Template-level',
    rule: 'Meta reports this per template per day, so it also counts other sends of the same template.',
  },
  unavailable: {
    label: 'Not available',
    rule: 'Meta did not report this for the broadcast.',
  },
}

/**
 * @param {unknown} value
 * @returns {boolean} True for a finite number.
 */
function isNumber(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

/**
 * Format a count; null/undefined/non-numeric -> "n/a" (a real 0 stays "0").
 * @param {unknown} value
 * @returns {string}
 */
export function formatCount(value) {
  return isNumber(value) ? value.toLocaleString() : NOT_AVAILABLE
}

/**
 * Format a percentage already expressed in percent (e.g. 98.2); null -> "n/a".
 * @param {unknown} value
 * @returns {string}
 */
export function formatRate(value) {
  return isNumber(value) ? `${value}%` : NOT_AVAILABLE
}

/**
 * Format money with the currency code Intl knows; no hardcoded symbols.
 * Falls back to "<code> <amount>" when the code is unknown to Intl and to
 * the bare number when no currency is given.
 * @param {unknown} amount
 * @param {string|null} currency - ISO 4217 code.
 * @returns {string}
 */
export function formatMoney(amount, currency) {
  if (!isNumber(amount)) return NOT_AVAILABLE
  if (!currency) return amount.toLocaleString()
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount)
  } catch {
    return `${currency} ${amount.toLocaleString()}`
  }
}

/**
 * Turn a snake_case / UPPER_CASE key into a readable label.
 * @param {string} key
 * @returns {string}
 */
export function humanizeKey(key) {
  const text = String(key ?? '').replace(/_/g, ' ').trim().toLowerCase()
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : ROUTE_LABELS.unknown
}

/**
 * Label for a send-route or pricing-category key; blank/unknown -> "Unknown route".
 * @param {string} key
 * @returns {string}
 */
export function routeLabel(key) {
  return ROUTE_LABELS[key] || humanizeKey(key)
}

/**
 * Entries of a count map as [{key,label,count}], sorted by count desc.
 * @param {Record<string, number>|null|undefined} map
 * @returns {Array<{key: string, label: string, count: number}>}
 */
export function breakdownRows(map) {
  return Object.entries(map || {})
    .filter(([, count]) => isNumber(count))
    .map(([key, count]) => ({ key, label: routeLabel(key), count }))
    .sort((a, b) => b.count - a.count)
}

/**
 * Render a conversions map as ["Website purchases: 3", ...]; empty/null -> [].
 * @param {Record<string, number>|null|undefined} conversions
 * @returns {string[]}
 */
export function conversionLines(conversions) {
  return Object.entries(conversions || {}).map(([name, n]) => `${humanizeKey(name)}: ${formatCount(n)}`)
}
