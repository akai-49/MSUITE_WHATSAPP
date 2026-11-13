/**
 * Shared API client factory.
 *
 * Every `services/*Api.js` file used to ship its own ~15 lines of
 * boilerplate: a `PREFIX` const, a `call(method, params)` wrapper, the
 * try/catch with `console.error(label, ...)`. We extract that here so
 * adding a new service module is two lines:
 *
 *   import { createApiClient } from './_factory'
 *   const call = createApiClient({ prefix: RPC.foo, label: 'Foo' })
 *
 * The factory also handles one shared quirk: frappe-ui's
 * `transformResponse` throws "Cannot read properties of undefined
 * (reading 'exc')" when the server returns a non-JSON response (HTML
 * login page after session timeout, proxy 502, …). Opt into the
 * friendly wrapper via `{ sessionTimeoutAware: true }`.
 *
 * On 401/403 or session expiry, the shared `handleSessionExpiry` helper
 * redirects the window to `/msuite-login?redirect-to=<current path>`.
 */
import { frappeRequest } from 'frappe-ui'
import { handleSessionExpiry, isSessionExpired } from '@/shared/utils/sessionExpiry'

const SESSION_EXPIRED_MESSAGE =
  'The server returned an unexpected response (often a session '
  + 'timeout). Please refresh the page or log in again, then retry.'

/**
 * Returns a `call(method, params)` function bound to a specific RPC
 * prefix + log label.
 *
 * @param {object}  opts
 * @param {string}  opts.prefix                Trailing-dot RPC prefix.
 * @param {string}  opts.label                 Used in console.error lines.
 * @param {boolean} [opts.sessionTimeoutAware] Re-throw "exc" errors as a
 *                                             friendly "session expired"
 *                                             message (default: false).
 * @returns {(method: string, params?: object) => Promise<any>}
 */
export function createApiClient({ prefix, label, sessionTimeoutAware = false }) {
  return async function call(method, params = {}) {
    try {
      return await frappeRequest({
        url: `/api/method/${prefix}${method}`,
        method: 'POST',
        params,
      })
    } catch (err) {
      handleSessionExpiry(err)
      if (sessionTimeoutAware && isSessionExpired(err)) {
        console.error(`${label} API non-JSON error`, method, err)
        const wrapped = new Error(SESSION_EXPIRED_MESSAGE)
        wrapped.cause = err
        throw wrapped
      }
      console.error(`${label} API error`, method, err)
      throw err
    }
  }
}

/**
 * Fire a single Frappe RPC without binding to any prefix. Used when a
 * service module needs to reach into a *different* module's RPC for
 * one call (e.g. Creative Library borrowing Ad Composer's
 * `list_ad_accounts`). Prefer prefix-bound `createApiClient` for
 * everything else.
 */
export function callRpc(fullMethod, params = {}, label = 'RPC') {
  return frappeRequest({
    url: `/api/method/${fullMethod}`,
    method: 'POST',
    params,
  }).catch((err) => {
    handleSessionExpiry(err)
    console.error(`${label} API error`, fullMethod, err)
    throw err
  })
}
