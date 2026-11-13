/**
 * Inbox API client.
 *
 * Every endpoint maps 1:1 to a whitelisted Frappe RPC on the client
 * app at `RPC.inbox` (see `@/shared/constants/api`).
 */
import { createApiClient } from '@/services/_factory'
import { RPC, FRAPPE_UPLOAD_URL } from '@/shared/constants/api'
import { GIF_PAGE_SIZE } from '../utils/richMedia'

const call = createApiClient({ prefix: RPC.inbox, label: 'Inbox' })
const callQuickReply = createApiClient({ prefix: RPC.quickReply, label: 'Quick Reply' })
const callRichMedia = createApiClient({ prefix: RPC.richMedia, label: 'Rich Media' })

// ── Conversation listing ────────────────────────────────────────────────

export function listConversations(filters = {}) {
  return call('list_conversations', filters)
}

export function getConversation(name) {
  return call('get_conversation', { name })
}

// ── Messages ────────────────────────────────────────────────────────────

export function listMessages(conversation, { limit = 50, start = 0, channel_type = null, exclude_channel_type = null } = {}) {
  const params = { conversation, limit, start }
  if (channel_type) params.channel_type = channel_type
  if (exclude_channel_type) params.exclude_channel_type = exclude_channel_type
  return call('list_messages', params)
}

export function sendMessage(conversation, payload = {}) {
  const targetConv = payload?.conversation || conversation
  return call('send_message', { ...payload, conversation: targetConv })
}

/**
 * Messenger card / button template flag + every limit the server enforces,
 * so the builder never hardcodes numbers.
 */
export function getMessengerTemplateRequirements() {
  return call('get_messenger_template_requirements')
}

export function listWhatsappTemplates(language = null, whatsappAccount = null) {
  const params = {}
  if (language) params.language = language
  if (whatsappAccount) params.whatsapp_account = whatsappAccount
  return call('list_whatsapp_templates', params)
}

/** Approved utility message templates of the Facebook Page behind a conversation. */
export function listMessengerUtilityTemplates(conversation) {
  return call('list_messenger_utility_templates', { conversation })
}

/**
 * Create a Messenger utility message template for the Facebook Page behind a conversation.
 * @param {object} params
 * @param {string} params.conversation
 * @param {string} params.name
 * @param {string} [params.language]
 * @param {string} [params.header]
 * @param {string} params.body
 * @param {object} [params.examples]
 * @returns {Promise<{id: string, status: string, name: string}>}
 */
export function createMessengerUtilityTemplate({ conversation, name, language, header, body, examples }) {
  return call('create_messenger_utility_template', {
    conversation,
    name,
    language,
    header,
    body,
    examples: JSON.stringify(examples || {}),
  })
}

export function listWhatsappFlows({ whatsappAccount = null, search = '' } = {}) {
  const params = {}
  if (whatsappAccount) params.whatsapp_account = whatsappAccount
  if (search) params.search = search
  return call('list_whatsapp_flows', params)
}

export function listWhatsappSendInboxes() {
  return call('list_whatsapp_send_inboxes')
}

export function listEmailSendInboxes() {
  return call('list_email_send_inboxes')
}

/**
 * Connected Facebook Pages / Instagram Business Accounts that can send on
 * this channel. Each row carries both the `inbox` and the `social_account`
 * — the backend needs both and validates that the pair belongs together.
 */
export function listSocialSendAccounts(channelType) {
  return call('list_social_send_accounts', { channel_type: channelType })
}

export function reactToMessage(channel_message, emoji) {
  return call('react_to_message', { channel_message, emoji: emoji || '' })
}

export function getConversationForParty(party_type, party_name, channel_type = null, exclude_channel_type = null) {
  const params = { party_type, party_name }
  if (channel_type) params.channel_type = channel_type
  if (exclude_channel_type) params.exclude_channel_type = exclude_channel_type
  return call('get_conversation_for_party', params)
}

/**
 * Upload an arbitrary file to Frappe's File store and return its
 * public URL. Multipart form-data can't go through frappeRequest, so
 * this is a bare fetch — the only place in this module that bypasses
 * the shared factory.
 */
export async function uploadFile(file, { isPrivate = 0, folder = 'Home/Attachments' } = {}) {
  const form = new FormData()
  form.append('file', file)
  form.append('is_private', String(isPrivate))
  form.append('folder', folder)
  const res = await fetch(FRAPPE_UPLOAD_URL, {
    method: 'POST',
    headers: {
      'X-Frappe-CSRF-Token': window.csrf_token || 'token',
    },
    credentials: 'include',
    body: form,
  })
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
  const data = await res.json()
  return data?.message || data
}

// ── Workflow ────────────────────────────────────────────────────────────

export function assign(conversation, user, team = null) {
  return call('assign', { conversation, user, team })
}

export function setStatus(conversation, status, snoozed_until = null) {
  return call('set_status', { conversation, status, snoozed_until })
}

export function setPriority(conversation, priority) {
  return call('set_priority', { conversation, priority })
}

export function markRead(conversation) {
  return call('mark_read', { conversation })
}

/** Server-side unread totals for the nav badge — not capped by page size. */
export function getUnreadSummary() {
  return call('get_unread_summary')
}

export function openTicket(conversation) {
  return call('open_ticket', { conversation })
}

export function linkParty(conversation, party_type, party_name) {
  return call('link_party', { conversation, party_type, party_name })
}

export function mergeHandles(handle_a, handle_b, crm_party_type, crm_party) {
  return call('merge_handles', { handle_a, handle_b, crm_party_type, crm_party })
}

// ── Manual-merge UI helpers ─────────────────────────────────────────────

export function listHandlesForParty(party_type, party_name) {
  return call('list_handles_for_party', { party_type, party_name })
}

export function listUnmatchedHandles({ excludeChannel, search, limit = 25 } = {}) {
  return call('list_unmatched_handles', {
    exclude_channel: excludeChannel,
    search,
    limit,
  })
}

/**
 * Retrieve inbox overview dashboard metrics.
 *
 * @param {string|object} [periodOrParams='today'] - Period key ('today', '7d', '30d') or params object
 * @returns {Promise<object>} Dashboard metrics payload
 */
export function getInboxDashboardMetrics(periodOrParams = 'today') {
  const params = typeof periodOrParams === 'object' && periodOrParams !== null
    ? periodOrParams
    : { period: periodOrParams }
  return call('get_inbox_dashboard_metrics', params)
}

export function createLeadForConversation(conversation) {
  return call('create_lead_for_conversation', { conversation })
}

export function startConversation(payload) {
  return call('start_conversation', payload)
}

export function deleteConversations(names) {
  return call('delete_conversations', { names })
}

export function getUnifiedLeadAiContext(conversation, lead_name = null) {
  return call('get_unified_lead_ai_context', { conversation, lead_name })
}

// ── Quick Replies ───────────────────────────────────────────────────────

/** List saved replies; `channel_type` also returns the "All channels" ones. */
export function listQuickReplies(filters = {}) {
  return callQuickReply('list_quick_replies', filters)
}

export function createQuickReply(payload) {
  return callQuickReply('create_quick_reply', payload)
}

export function updateQuickReply(name, patch) {
  return callQuickReply('update_quick_reply', { name, ...patch })
}

export function deleteQuickReply(name) {
  return callQuickReply('delete_quick_reply', { name })
}

// ── Rich media (GIFs, voice notes) ──────────────────────────────────────

/**
 * Search GIFs or stickers via GIPHY; blank query = trending.
 * Accepts positional parameters `(query, limit, offset, kind, { signal })`
 * or a single `params` object `{ query, limit, offset, kind, signal }`.
 *
 * @param {string|object} [query=''] - Search term string or params object.
 * @param {number|object} [limit=GIF_PAGE_SIZE] - Page size limit or options if query is an object.
 * @param {number} [offset=0] - Result offset for pagination.
 * @param {'gifs'|'stickers'} [kind='gifs'] - GIPHY media catalogue ('gifs' or 'stickers').
 * @param {object} [options={}] - Options object.
 * @param {AbortSignal} [options.signal] - AbortSignal to cancel in-flight request.
 * @returns {Promise<{ configured: boolean, results: Array, next_offset: number|null }>}
 */
export function searchGifs(query = '', limit = GIF_PAGE_SIZE, offset = 0, kind = 'gifs', { signal } = {}) {
  let params
  let sig = signal

  if (typeof query === 'object' && query !== null) {
    params = { ...query }
    const opts = (limit && typeof limit === 'object') ? limit : {}
    sig = params.signal || opts.signal
    delete params.signal
  } else {
    params = { query, limit, offset, kind }
  }

  if (sig?.aborted) {
    return Promise.reject(new DOMException('The user aborted a request.', 'AbortError'))
  }

  const promise = callRichMedia('search_gifs', params)
  if (!sig) return promise

  return new Promise((resolve, reject) => {
    const onAbort = () => {
      sig.removeEventListener('abort', onAbort)
      reject(new DOMException('The user aborted a request.', 'AbortError'))
    }
    sig.addEventListener('abort', onAbort)
    promise
      .then((res) => {
        sig.removeEventListener('abort', onAbort)
        resolve(res)
      })
      .catch((err) => {
        sig.removeEventListener('abort', onAbort)
        reject(err)
      })
  })
}

/** Convert an uploaded recording to the channel's audio format. Returns { file_url, file_name, mime_type }. */
export function prepareVoiceNote(fileUrl, channelType) {
  return callRichMedia('prepare_voice_note', { file_url: fileUrl, channel_type: channelType })
}

/** Convert a GIPHY sticker URL to a WhatsApp-ready WebP file. Returns { file_url, file_name, mime_type, animated }. */
export function prepareSticker(url) {
  return callRichMedia('prepare_sticker', { url })
}
