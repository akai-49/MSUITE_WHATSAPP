/**
 * Helpers for WhatsApp Consent bulk operations.
 */

const HEADER_TOKENS = new Set([
  'phone',
  'phones',
  'mobile',
  'telephone',
  'number',
  'contact',
  'phone_number',
  'phone number',
  'phonenumber',
  'msisdn',
  'cell',
  'cellphone',
])

/**
 * Parse a raw string of numbers (newline, comma, semicolon separated) or CSV/TXT content.
 * Cleans formatting, ignores headers, and deduplicates.
 *
 * @param {string} rawText
 * @returns {string[]} Array of unique candidate numbers
 */
export function parseNumbers(rawText) {
  if (!rawText || typeof rawText !== 'string') {
    return []
  }

  // Remove BOM if present
  const text = rawText.replace(/^\uFEFF/, '')
  const rawTokens = text.split(/[\r\n,;]+/)

  const seen = new Set()
  const result = []

  for (let token of rawTokens) {
    token = token.trim()
    // Strip surrounding quotes
    token = token.replace(/^["']|["']$/g, '').trim()
    if (!token) continue

    const lower = token.toLowerCase()
    if (HEADER_TOKENS.has(lower)) {
      continue
    }

    if (!seen.has(token)) {
      seen.add(token)
      result.push(token)
    }
  }

  return result
}

/**
 * Chunk an array of items into sub-arrays of at most chunkSize.
 *
 * @template T
 * @param {T[]} items
 * @param {number} [chunkSize=5000]
 * @returns {T[][]}
 */
export function chunkNumbers(items, chunkSize = 5000) {
  if (!Array.isArray(items) || items.length === 0) {
    return []
  }
  if (!chunkSize || chunkSize <= 0) {
    return [items]
  }

  const chunks = []
  for (let i = 0; i < items.length; i += chunkSize) {
    chunks.push(items.slice(i, i + chunkSize))
  }
  return chunks
}

/**
 * Sum an array of consent API results.
 * Each item has { updated, not_found, invalid }.
 *
 * @param {Array<{ updated?: number, not_found?: number, invalid?: number }>} results
 * @returns {{ updated: number, not_found: number, invalid: number }}
 */
export function sumConsentResults(results) {
  const total = {
    updated: 0,
    not_found: 0,
    invalid: 0,
  }

  if (!Array.isArray(results)) {
    return total
  }

  for (const res of results) {
    if (!res) continue
    total.updated += Number(res.updated) || 0
    total.not_found += Number(res.not_found) || 0
    total.invalid += Number(res.invalid) || 0
  }

  return total
}
