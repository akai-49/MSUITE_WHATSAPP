/**
 * Shared input format hints and preview fallbacks.
 *
 * All values here are format hints or empty-state labels only.
 * They contain no real-looking personal data, phone numbers, or third-party domains.
 * Reserved RFC 2606 domains ('example.com') are used exclusively for format illustration.
 */

/** Format hint only: RFC 2606 reserved example email. */
export const EXAMPLE_EMAIL = 'name@example.com'

/** Format hint only: E.164 international phone number structure hint. */
export const EXAMPLE_PHONE_HINT = '+<country code><number>'

/** Format hint only: RFC 2606 reserved example HTTPS web URL. */
export const EXAMPLE_URL = 'https://example.com'

/** Format hint only: RFC 2606 vanity URL path format hint. */
export const EXAMPLE_URL_PATH_HINT = 'example.com/path'

/** Format hint only: RFC 2606 reserved example domain. */
export const EXAMPLE_DOMAIN = 'example.com'

/** Empty-state label for ad preview display when destination URL is unset. */
export const PREVIEW_URL_EMPTY_LABEL = 'Your website'
