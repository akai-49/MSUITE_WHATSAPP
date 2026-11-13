/**
 * Shared helpers for template variable preview substitutions.
 *
 * Renders human-readable variable labels in message/email/WhatsApp previews
 * instead of fake names, emails, or phone numbers.
 */

/** Known friendly labels for common template variable identifiers. */
const SPECIAL_LABELS = {
  recipient_name: 'Recipient name',
  first_name: 'First name',
  last_name: 'Last name',
  full_name: 'Full name',
  email_address: 'Email address',
  email: 'Email address',
  mobile_number: 'Mobile number',
  phone_number: 'Phone number',
  phone: 'Phone number',
  unsubscribe_url: 'Unsubscribe link',
  unsubscribe_link: 'Unsubscribe link',
  company_name: 'Company name',
  company: 'Company',
  organization: 'Organization',
  street_address: 'Street address',
  city: 'City',
  state: 'State',
  province: 'Province',
  country: 'Country',
  zip_code: 'Zip code',
  post_code: 'Post code',
  date_of_birth: 'Date of birth',
  gender: 'Gender',
  marital_status: 'Marital status',
  relationship_status: 'Relationship status',
  job_title: 'Job title',
  work_email: 'Work email',
  work_phone_number: 'Work phone number',
  whatsapp_number: 'WhatsApp number',
}

/**
 * Escape unsafe HTML characters in a string.
 *
 * @param {string|null|undefined} str Raw text string.
 * @returns {string} HTML-escaped string safe for injection into markup.
 */
export function escapeHtml(str) {
  if (str == null) return ''
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * Return a human-readable label for a template variable key.
 *
 * E.g. 'recipient_name' -> 'Recipient name', '1' -> 'Variable 1'.
 *
 * @param {string|null|undefined} variableKey Template variable identifier.
 * @returns {string} Friendly capitalized label.
 */
export function previewLabelFor(variableKey) {
  if (variableKey == null || variableKey === '') return ''

  const key = String(variableKey).trim()
  if (!key) return ''

  // Numeric ordinal variables (e.g. WhatsApp {{1}}, {{2}})
  if (/^\d+$/.test(key)) {
    return `Variable ${key}`
  }

  const normalized = key.toLowerCase()
  if (SPECIAL_LABELS[normalized]) {
    return SPECIAL_LABELS[normalized]
  }

  // Fallback: replace underscores/dashes with spaces and capitalize first letter
  const cleaned = key.replace(/[_-]+/g, ' ').trim().toLowerCase()
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1)
}

/**
 * Replace {{ variable }} placeholders in a template with resolved values or labels.
 *
 * @param {string|null|undefined} template Template string containing {{ var }} placeholders.
 * @param {(key: string) => string} resolver Function mapping variable key to replacement string.
 * @param {{ escapeHtml?: boolean }} [options] Formatting options.
 * @returns {string} Rendered preview string.
 */
export function fillPreview(template, resolver, options = {}) {
  if (typeof template !== 'string') return ''

  const escapeFn = options.escapeHtml ? escapeHtml : (val) => val

  return template.replace(/\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}/g, (_match, key) => {
    let resolved = resolver ? resolver(key) : ''
    if (resolved === undefined || resolved === null || resolved === '') {
      resolved = previewLabelFor(key)
    }
    return escapeFn(resolved != null ? String(resolved) : key)
  })
}
