/**
 * Meta Multi-Product Message (MPM) limits & validation (M12)
 *
 * Meta constraints:
 * - Section title: max 24 characters
 * - Sections: 1 to 10 sections
 * - Total products across all sections: 1 to 30 products
 */

export const MPM_LIMITS = {
  MAX_SECTION_TITLE_LENGTH: 24,
  MIN_SECTIONS: 1,
  MAX_SECTIONS: 10,
  MIN_PRODUCTS: 1,
  MAX_PRODUCTS: 30,
}

export function validateMpmSectionTitle(title) {
  const str = String(title || '')
  if (str.length > MPM_LIMITS.MAX_SECTION_TITLE_LENGTH) {
    return {
      valid: false,
      error: `Section title exceeds ${MPM_LIMITS.MAX_SECTION_TITLE_LENGTH} characters (currently ${str.length}).`,
    }
  }
  return { valid: true }
}

export function validateMpmProductCount(count) {
  if (count > MPM_LIMITS.MAX_PRODUCTS) {
    return {
      valid: false,
      error: `Cannot exceed ${MPM_LIMITS.MAX_PRODUCTS} products total (Meta WhatsApp limit).`,
    }
  }
  if (count < MPM_LIMITS.MIN_PRODUCTS) {
    return {
      valid: false,
      error: 'At least one product is required for Multi-Product Messages.',
    }
  }
  return { valid: true }
}

export function canAddMpmProduct(currentCount) {
  return currentCount < MPM_LIMITS.MAX_PRODUCTS
}
