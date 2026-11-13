/**
 * Label for a template's category in the Insights table.
 *
 * Never invents a category: a missing, non-string or blank value yields the
 * explicit "Unknown" label instead of a made-up default.
 *
 * @param {unknown} category - Category from the API (e.g. "MARKETING").
 * @returns {string} The trimmed category, or "Unknown".
 */
export function templateCategoryLabel(category) {
  if (typeof category !== 'string') return 'Unknown'
  const trimmed = category.trim()
  return trimmed || 'Unknown'
}

/**
 * Count for the Insights cards where `null` means "Meta/our data has none".
 *
 * Unlike `value || 0`, a missing value is never shown as a fake zero.
 *
 * @param {unknown} value - Count from the API (number, null or undefined).
 * @returns {string|number} "n/a" for null/undefined/non-numeric, else the number (a real 0 stays 0).
 */
export function countOrNa(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 'n/a'
}

/**
 * Money cell for the Insights charges card; null is "n/a", not 0.00.
 *
 * @param {unknown} value - Amount from the API.
 * @param {string} symbol - Currency prefix already resolved by the caller.
 * @returns {string} "n/a", or symbol + amount with two decimals.
 */
export function chargeOrNa(value, symbol) {
  const num = typeof value === 'string' ? parseFloat(value) : value
  return typeof num === 'number' && Number.isFinite(num) ? `${symbol}${num.toFixed(2)}` : 'n/a'
}
