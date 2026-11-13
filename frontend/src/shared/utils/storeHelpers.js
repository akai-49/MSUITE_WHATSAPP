/**
 * Shared store helpers — used by every Pinia editor (Ad Composer,
 * Ad Creative Editor, Social Composer, Lead Gen Form Editor, …).
 *
 * Both helpers used to be duplicated inside each store. The copies
 * drifted (adCreativeEditor's `prettifyFrappeError` only handled 2 of
 * the 5 shapes Frappe actually emits, so its banners showed
 * "Could not save." instead of the real reason). This module is the
 * single source of truth — extend here, every editor benefits.
 */


/**
 * Prettify a Frappe error payload into a single human-readable line.
 *
 * Frappe surfaces errors in several shapes depending on whether the
 * throw was a `frappe.throw` / `msgprint` / unhandled exception, and
 * how `frappeRequest` re-throws them. This helper walks every known
 * location so the SPA shows "Campaign spending limit must be at least
 * ₹5,000" instead of the bare "Internal Server Error" wrapper.
 *
 * Shapes covered (in priority order):
 *   1. Structured `messages` array — frappe.throw default.
 *   2. `_server_messages` JSON-string — older Frappe shape.
 *   3. `exception` / `exc` traceback — last "Module.ExcClass: msg" line.
 *   4. `.body` property — when frappeRequest unpacks JSON itself.
 *   5. Plain `e.message` — JS Error / network failure.
 *
 * @param {unknown} e          Anything that was caught.
 * @param {string}  [logLabel] If set, the raw payload is `console.debug`-logged
 *                             under this label so dev tools show the shape that
 *                             matched (or didn't). Stripped by terser in prod.
 * @returns {string} Human-readable message — never empty unless `e` is falsy.
 */
function prettifyRaw(e, logLabel = '') {
  if (!e) return ''

  if (logLabel) {
    try { console.debug(logLabel, e) } catch { /* console may be unavailable */ }
  }

  // 1. Structured messages array (frappe.throw default shape).
  const msgs = e.messages
    || e?.exc_response?.messages
    || e?._server_messages_parsed
  if (Array.isArray(msgs) && msgs.length) {
    const first = msgs[0]
    if (typeof first === 'string') {
      // Some Frappe codepaths nest JSON inside the string — unwrap if so.
      try {
        const parsed = JSON.parse(first)
        if (parsed?.message) return parsed.message
      } catch { /* not JSON — use as-is */ }
      return first
    }
    if (first?.message) return first.message
  }

  // 2. _server_messages as a JSON-string (older Frappe shape).
  const sm = e._server_messages || e?.exc_response?._server_messages
  if (typeof sm === 'string') {
    try {
      const arr = JSON.parse(sm)
      const first = typeof arr[0] === 'string' ? JSON.parse(arr[0]) : arr[0]
      if (first?.message) return first.message
    } catch { /* fall through */ }
  }

  // 3. `exception` / `exc` traceback — last "<Module>.<ExcClass>: <msg>"
  // line is what frappe.throw produces. For Meta publish errors the
  // message after the colon is exactly the Graph API rejection.
  const exc = e.exception || e.exc || e?.exc_response?.exception
  if (typeof exc === 'string') {
    const lines = exc.split('\n').map((l) => l.trim()).filter(Boolean)
    for (let i = lines.length - 1; i >= 0; i--) {
      const m = lines[i].match(/^[\w.]+\.([A-Z][\w]*(?:Error|Exception)):\s*(.+)$/)
      if (m) return m[2]
    }
    if (lines.length) return lines[lines.length - 1]
  }

  // 4. `.body` property — frappeRequest sometimes returns parsed JSON
  //    in `.body` instead of bubbling up via `messages`.
  const body = e?.body
  if (body) {
    if (typeof body === 'string')      return body
    if (body.message)                  return body.message
    if (Array.isArray(body.messages))  return body.messages[0]?.message || body.messages[0]
  }

  // 5. Plain Error / Promise rejection / unknown shape.
  return e.message || String(e)
}


/**
 * Replace `target`'s contents with `source`'s WITHOUT changing
 * target's object identity.
 *
 * Why this exists: components hold `state` via prop binding or store
 * destructuring. A plain `this.state = { ... }` re-assign would orphan
 * those references and cause "preview won't update" / "field shows
 * stale value" bugs. We mutate-in-place so every consumer keeps a live
 * reference.
 *
 * Algorithm:
 *   1. Delete keys on target that aren't in source (clears stale state
 *      from a previous load — e.g. `boost_preview` after navigating
 *      back to a fresh draft).
 *   2. Copy every source key onto target.
 *
 * @param {object} target Pinia store state slot (mutated in place).
 * @param {object} source New full state.
 */
export function replaceInPlace(target, source) {
  for (const key of Object.keys(target)) {
    if (!(key in source)) delete target[key]
  }
  Object.assign(target, source)
}


/**
 * Frappe wraps parts of its messages in HTML (`Insufficient Permission for <strong>CRM Deal</strong>`).
 * Rendered as text that shows the raw tags, so every message is reduced to plain text here, and the
 * one failure people actually hit — a missing permission — is turned into a sentence they can act on.
 */
export function toPlainText(html) {
  if (html == null) return ''
  let t = String(html)
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#0*39;/g, "'")
  return t.replace(/\s+/g, ' ').trim()
}

export function prettifyFrappeError(e, logLabel = '') {
  const msg = toPlainText(prettifyRaw(e, logLabel))
  const perm = msg.match(/^Insufficient Permission(?: for (.+))?$/i)
  if (perm) {
    const what = perm[1] ? ` ${perm[1].trim()}` : ' this'
    return `You don't have permission to open${what}. Ask an admin to check your role in Settings → Users & Access.`
  }
  return msg
}
