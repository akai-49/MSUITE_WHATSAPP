/**
 * Central session-expiry and 401/403 authentication error handler.
 *
 * Redirects the user to `/login?redirect-to=<current path>` when:
 * 1. An API response returns HTTP 401 or 403
 * 2. Frappe returns a SessionExpired error or non-JSON login redirect
 */

const SESSION_EXPIRED_NEEDLES = ["reading 'exc'", 'reading "exc"', 'SessionExpired']

export function isSessionExpired(err) {
  if (!err) return false

  const status = err.status || err.response?.status || err.statusCode
  if (status === 401 || status === 403) {
    return true
  }

  const msg = err.message || String(err || '')
  if (SESSION_EXPIRED_NEEDLES.some((needle) => msg.includes(needle))) {
    return true
  }

  if (err.exc_type === 'SessionExpired') {
    return true
  }

  return false
}

export function buildLoginRedirectUrl(currentPath) {
  const path = currentPath
    || (typeof window !== 'undefined' ? (window.location.pathname + window.location.search) : '/crm')
  // The panel runs inside Frappe CRM, which signs in at /login.
  if (path.startsWith('/login')) {
    return '/login'
  }
  return `/login?redirect-to=${encodeURIComponent(path)}`
}

export function handleSessionExpiry(err, currentPath) {
  if (!isSessionExpired(err)) {
    return false
  }

  if (typeof window !== 'undefined') {
    const dest = buildLoginRedirectUrl(currentPath)
    if (window.location && typeof window.location.assign === 'function') {
      window.location.assign(dest)
    } else if (window.location) {
      window.location.href = dest
    }
  }
  return true
}
