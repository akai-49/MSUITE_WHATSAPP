/**
 * @file External vendor and documentation link constants.
 *
 * Centralizes external links used across workspace components (Meta Ads /
 * Events Manager, WhatsApp Business Manager, Plivo Console, and vendor docs).
 */

/**
 * Meta Events Manager overview and pixel settings URL.
 * Used in Ad Composer Brief step for pixel setup guidance.
 * @type {string}
 */
export const META_EVENTS_MANAGER_URL = 'https://business.facebook.com/events_manager2'

/**
 * Meta Ads Manager audiences manage view.
 * Used as fallback link when no saved audiences exist in the workspace.
 * @type {string}
 */
export const META_ADS_MANAGER_AUDIENCES_URL = 'https://www.facebook.com/adsmanager/audiences/manage'

/**
 * Meta Ads Manager campaigns overview deep link.
 * Used in Ads Manager dashboard table to open campaigns in Meta native tools.
 * @type {string}
 */
export const META_ADS_MANAGER_CAMPAIGNS_URL = 'https://adsmanager.facebook.com/adsmanager/manage/campaigns'

/**
 * Meta Business Help center article explaining custom audiences.
 * @type {string}
 */
export const META_HELP_CUSTOM_AUDIENCES_URL = 'https://www.facebook.com/business/help/744354708981227'

/**
 * Meta Business Help center article explaining daily ad budgets and pacing.
 * @type {string}
 */
export const META_HELP_DAILY_BUDGET_URL = 'https://www.facebook.com/business/help/1407035012879555'

/**
 * WhatsApp Business Manager portal overview link.
 * Used in WhatsApp template editor to configure calling permissions.
 * @type {string}
 */
export const WHATSAPP_MANAGER_URL = 'https://business.facebook.com/wa/manage/'

/**
 * Meta documentation for WhatsApp Cloud API phone number settings and calling.
 * @type {string}
 */
export const WHATSAPP_DOCS_CALLING_URL = 'https://developers.facebook.com/docs/whatsapp/cloud-api/phone-numbers/settings'

/**
 * Plivo Console phone numbers search and procurement URL.
 * Used in AI Calling assistant settings to buy inbound voice numbers.
 * @type {string}
 */
export const PLIVO_CONSOLE_PHONE_NUMBERS_SEARCH_URL = 'https://console.plivo.com/phone-numbers/search/'
