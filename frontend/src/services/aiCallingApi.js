/**
 * AI Calling — Service layer.
 *
 * All RPC methods live in ai_calling.ai_calling.api.*
 * We use callRpc (one-off calls without prefix binding) because
 * the backend module prefix differs from msuite_workspace.
 */
import { callRpc } from './_factory'

const PREFIX = 'ai_calling.ai_calling.api.'

function call(method, params = {}) {
  return callRpc(`${PREFIX}${method}`, params, 'AI-Calling')
}

// ── Dashboard / Overview ─────────────────────────────────────────────────────

export function getAiCallingStats({ days } = {}) {
  return call('get_ai_calling_stats', days ? { days } : undefined)
}

export function getActiveBroadcasts() {
  return call('get_active_broadcasts')
}

// ── Voice Broadcasts (Broadcasts) ─────────────────────────────────────────────────

export function getBroadcasts({ status, search, limit, start } = {}) {
  return call('get_broadcasts', { status, search, limit, start })
}

export function getBroadcastDetail(campaignName) {
  return call('get_broadcast_detail', { broadcast: campaignName })
}

/** Start / pause / resume / stop a broadcast via its doc method.
 *  Valid actions: 'start_broadcast' | 'pause_broadcast' | 'resume_broadcast' | 'complete_broadcast'
 */
export function broadcastAction(campaignName, action) {
  return callRpc('run_doc_method', {
    dt: 'AI Calling Broadcast',
    dn: campaignName,
    method: action,
  }, 'AI-Calling')
}

export function refreshBroadcastAnalytics(campaignName) {
  return callRpc(
    'ai_calling.ai_calling.doctype.ai_calling_broadcast.ai_calling_broadcast.refresh_broadcast_analytics',
    { broadcast: campaignName },
    'AI-Calling',
  )
}

/**
 * Creates a new AI Calling Broadcast with the given leads and schedule configuration.
 *
 * @param {object} params
 * @param {string}   params.campaignName
 * @param {string}   params.language
 * @param {string}   params.productKb
 * @param {string[]} params.leadNames
 * @param {string}   [params.startDate]       ISO date string, e.g. "2026-07-20"
 * @param {string}   [params.endDate]         ISO date string
 * @param {string}   [params.callStart]       "HH:MM" time string
 * @param {string}   [params.callEnd]         "HH:MM" time string
 * @param {string[]} [params.callDays]        e.g. ["Mon","Tue","Wed","Thu","Fri"]
 * @param {number}   [params.maxPerHour]      max calls per hour
 * @param {number}   [params.maxParallel]     max parallel calls
 * @param {number}   [params.retryCount]      retry count
 * @param {string}   [params.timezone]        IANA timezone string
 * @param {boolean}  [params.scheduleLater]   if true, don't start immediately
 */
export function createBroadcastFromLeads({
  campaignName,
  assistant,
  language,
  productKb,
  instructionsKb,
  leadNames,
  startDate,
  endDate,
  callStart,
  callEnd,
  callDays,
  maxPerHour,
  maxParallel,
  retryCount,
  timezone,
  scheduleLater,
  phoneNumber,
  description,
  broadcastInstructions,
  infoFields,
}) {
  return callRpc(
    'ai_calling.ai_calling.doctype.ai_calling_broadcast.ai_calling_broadcast.create_broadcast_from_leads',
    {
      broadcast_name: campaignName,
      broadcast: campaignName,
      phone_number: phoneNumber || '',
      description: description || '',
      broadcast_instructions: broadcastInstructions || '',
      info_fields_to_collect: infoFields?.length ? JSON.stringify(infoFields) : '',
      assistant: assistant || '',
      language,
      product_kb: productKb,
      instructions_kb: instructionsKb || '',
      lead_names: JSON.stringify(leadNames),
      start_date: startDate || '',
      end_date: endDate || '',
      calling_start_time: callStart || '',
      calling_end_time: callEnd || '',
      calling_days: callDays ? JSON.stringify(callDays) : '',
      max_calls_per_hour: maxPerHour || '',
      max_parallel_calls: maxParallel || '',
      // 0 is "no retries", not unset.
      retry_count: retryCount ?? '',
      timezone: timezone || '',
      schedule_later: scheduleLater ? '1' : '0',
    },
    'AI-Calling',
  )
}

// ── Unified Call Logs ────────────────────────────────────────────────────────

export function getUnifiedCallLogs({ callType, outcome, search, hasRecording, hasFlags, limit, start } = {}) {
  return call('get_unified_call_logs', {
    call_type: callType,
    outcome,
    search,
    has_recording: hasRecording ? 1 : 0,
    has_flags: hasFlags ? 1 : 0,
    limit,
    start,
  })
}

// ── Flagged Calls ────────────────────────────────────────────────────────────

export function getFlaggedCalls({ search, flagType, agent, limit, start } = {}) {
  return call('get_flagged_calls', { search, flag_type: flagType, agent, limit, start })
}

export function markCallReviewed(callLogName, managerNote = '') {
  return call('mark_call_reviewed', { call_log_name: callLogName, manager_note: managerNote })
}

// ── My Calls (Human Call) ────────────────────────────────────────────────────

export function getMyCalls({ search, outcome, callType, limit, start } = {}) {
  return call('get_my_calls', { search, outcome, call_type: callType, limit, start })
}

// ── Inbound Config ───────────────────────────────────────────────────────────

export function getInboundConfigs() {
  return call('get_inbound_configs')
}

export function saveInboundConfig(configName, data) {
  return call('save_inbound_config', { config_name: configName, ...data })
}

export function createInboundConfig(data) {
  return callRpc('frappe.client.insert', {
    doc: {
      doctype: 'AI Calling Inbound Config',
      is_active: 1,
      recording_enabled: 1,
      ...data,
    }
  }, 'AI-Calling')
}

// ── Recipients ───────────────────────────────────────────────────────────────

export function getRecipients({ broadcast, search, limit, start } = {}) {
  return call('get_broadcast_recipients', { broadcast, search, limit, start })
}

// ── Knowledge Bases & Phone Numbers (for dropdowns) ──────────────────────────

export function getKnowledgeBases(callType) {
  return call('get_knowledge_bases', callType ? { call_type: callType } : {})
}

export function getPhoneNumbers() {
  return call('get_phone_numbers')
}

// ── Recent Inbound Calls (mini-log) ──────────────────────────────────────────

export function getRecentInboundCalls(phoneNumber, limit = 5) {
  return call('get_recent_inbound_calls', { phone_number: phoneNumber, limit })
}

// ── AI Calling Knowledge Base CRUD ──────────────────────────────────────────────────

export function getVoiceKBList() {
  return callRpc('frappe.client.get_list', {
    doctype: 'AI Calling Knowledge Base',
    fields: ['name', 'kb_name', 'kb_type', 'description', 'content_type', 'content', 'attachment', 'status', 'ingestion_status', 'modified', 'ingestion_error'],
    order_by: 'modified desc',
  }, 'AI-Calling')
}

export function getVoiceKBDetail(name) {
  return callRpc('frappe.client.get_doc', {
    doctype: 'AI Calling Knowledge Base',
    name,
  }, 'AI-Calling')
}

export function createVoiceKB(data) {
  return callRpc('frappe.client.insert', {
    doc: {
      doctype: 'AI Calling Knowledge Base',
      status: 'Active',
      ...data,
    }
  }, 'AI-Calling')
}

export function updateVoiceKB(name, data) {
  return callRpc('frappe.client.set_value', {
    doctype: 'AI Calling Knowledge Base',
    name,
    fieldname: data,
  }, 'AI-Calling')
}

export function deleteVoiceKB(name) {
  return callRpc('frappe.client.delete', {
    doctype: 'AI Calling Knowledge Base',
    name,
  }, 'AI-Calling')
}

// ── Media Library (AI Calling Media) ─────────────────────────────────────────

export function getMediaLibrary() {
  return call('get_media_library')
}

export function createMedia({ title, description, fileUrl }) {
  return call('create_media', { title, description, file_url: fileUrl })
}

export function updateMedia(name, { title, description, fileUrl } = {}) {
  return call('update_media', { name, title, description, file_url: fileUrl })
}

export function deleteMedia(name) {
  return call('delete_media', { name })
}

// ── AI Calling Setup (Organization Config + KB child table) ──────────────────

export function getCrmOrganizations() {
  return call('get_crm_organizations')
}

/** Create a CRM Organization from the Setup page (fresh-site onboarding). */
export function createCrmOrganization(params) {
  if (typeof params === 'string') {
    return call('create_crm_organization', { organization_name: params })
  }
  return call('create_crm_organization', {
    organization_name: params.organizationName,
    website: params.website,
    no_of_employees: params.noOfEmployees,
    annual_revenue: params.annualRevenue,
    industry: params.industry,
    territory: params.territory,
    currency: params.currency,
    address: params.address,
    exchange_rate: params.exchangeRate,
  })
}

export function getIndustriesList() {
  return callRpc('frappe.client.get_list', { doctype: 'CRM Industry', fields: ['name'], limit: 100 }, 'AI-Calling')
}

export function getTerritoriesList() {
  return callRpc('frappe.client.get_list', { doctype: 'CRM Territory', fields: ['name'], limit: 100 }, 'AI-Calling')
}

export function getCurrenciesList() {
  return callRpc('frappe.client.get_list', { doctype: 'Currency', fields: ['name'], limit: 100 }, 'AI-Calling')
}

export function getAddressesList() {
  return callRpc('frappe.client.get_list', { doctype: 'Address', fields: ['name'], limit: 100 }, 'AI-Calling')
}

export function getNumberSetups() {
  return call('get_number_setups')
}

export function saveNumberSetup({
  name,
  organization,
  assignedDid,
  connectionName,
  description,
  activeAgentType,
  isActive,
}) {
  return call('save_number_setup', {
    name,
    organization,
    assigned_did: assignedDid,
    connection_name: connectionName,
    description,
    active_agent_type: activeAgentType,
    is_active: isActive ? 1 : 0,
  })
}

export function deleteAiSetupConfig(name) {
  return call('delete_number_setup', { name })
}

export function getAssistantConfigs() {
  return call('get_assistant_configs')
}

export function saveAssistantConfig(assistant, configData) {
  if (typeof assistant === 'object' && assistant !== null) {
    const { name, ...rest } = assistant
    return call('save_assistant_config', {
      assistant: name || assistant.assistant,
      config: JSON.stringify(rest),
    })
  }
  return call('save_assistant_config', {
    assistant,
    config: JSON.stringify(configData),
  })
}

export function deleteAssistantConfig(name) {
  return call('delete_assistant_config', { name })
}

/**
 * Resolve a playable URL for a call recording (presigned S3 or direct).
 * source: 'AI Calling Call Log' | 'AI Calling Human Call'
 */
export function getConnectedAccounts() {
  return callRpc('msuite_core.api.v1.app.connect.sync.get_connected_accounts', {}, 'AI-Calling')
}

export function getRecordingPlaybackUrl(source, name) {
  return call('get_recording_playback_url', { source, name })
}

export function getFileList() {
  return callRpc('frappe.client.get_list', {
    doctype: 'File',
    fields: ['file_name', 'file_url', 'file_size', 'owner', 'creation', 'modified'],
    limit: 1000,
  }, 'AI-Calling')
}

export function uploadKBFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('is_private', 0)
  formData.append('folder', 'Home')

  const headers = {}
  if (window.csrf_token && window.csrf_token !== '{{ csrf_token }}') {
    headers['X-Frappe-CSRF-Token'] = window.csrf_token
  }

  return fetch('/api/method/upload_file', {
    method: 'POST',
    headers,
    body: formData,
  }).then(res => {
    if (!res.ok) throw new Error('Upload failed')
    return res.json()
  })
}

// ── Bulk Contact Import (AI Call Bulk List) ───────────────────────────────────

export function getBulkLists() {
  return call('get_recipients_lists')
}

export function getBulkListDetail(name) {
  return call('get_recipients_list_detail', { name })
}

export function createBulkList(data) {
  return call('create_recipients_list', data)
}

export function deleteBulkList(name) {
  return call('delete_recipients_list', { name })
}

export function deleteBroadcasts(names) {
  return call('delete_broadcasts', { names: JSON.stringify(names) })
}

// ── Human Agent Click-to-Call ────────────────────────────────────────────────

export function initiateHumanCall({ lead, agentPhone, customerPhone }) {
  return call('initiate_human_call', {
    lead,
    agent_phone: agentPhone,
    customer_phone: customerPhone,
  })
}

export function initiateBrowserCall({ lead, customerPhone }) {
  return call('initiate_browser_call', {
    lead,
    customer_phone: customerPhone,
  })
}

export function saveHumanCallNote({ lead, noteContent }) {
  return call('save_human_call_note', {
    lead,
    note_content: noteContent,
  })
}

export function hangupBrowserCall({ callId }) {
  return call('hangup_browser_call', {
    call_id: callId,
  })
}

// ── Multi-Assistant Configuration ────────────────────────────────────────────

export function getAssistants({ search, callType } = {}) {
  return call('get_assistants', { search, call_type: callType })
}

export function createAssistant({ assistantName, assistantType }) {
  return call('create_assistant', {
    assistant_name: assistantName,
    assistant_type: assistantType,
  })
}

export function getAssistantDetail(assistantId) {
  return call('get_assistant_detail', { assistant: assistantId })
}

// Knowledge-graph sources this workspace may give its assistants (allowed by the provider),
// as { status: 'ok' | 'unavailable', options: [{ key, name }], message? }.
export function getKnowledgeSourceOptions() {
  return call('get_knowledge_source_options')
}

// The Gemini Live models an assistant may use, with each one's temperature range (from Google,
// through the voice backend); [] when it cannot say.
export function getLiveModels() {
  return call('get_live_models')
}

export function deleteAssistant(assistantId) {
  return call('delete_assistant', { assistant: assistantId })
}

export function getAvailableNumbers() {
  return call('get_available_numbers')
}

export function checkNumberInboundConflict(numberSetup, assistantId) {
  return call('check_number_inbound_conflict', {
    number_setup: numberSetup,
    assistant: assistantId,
  })
}

export function attachNumberToAssistant(assistantId, numberSetup, forceReassign = false) {
  return call('attach_number_to_assistant', {
    assistant: assistantId,
    number_setup: numberSetup,
    force_reassign: forceReassign ? 1 : 0,
  })
}


// ── Website voice widget (ai_calling.ai_calling.widget) ─────────────────────

export function listWebWidgets(assistantId) {
  return callRpc('ai_calling.ai_calling.widget.list_widgets', { assistant: assistantId }, 'AI-Calling')
}

export function saveWebWidget(assistantId, data, name = null) {
  const params = { assistant: assistantId, data: JSON.stringify(data) }
  if (name) params.name = name
  return callRpc('ai_calling.ai_calling.widget.save_widget', params, 'AI-Calling')
}

// A signed test session for the rep (ai_calling.ai_calling.sandbox); used by the widget preview.
export function startSandboxSession(assistantId) {
  return callRpc('ai_calling.ai_calling.sandbox.start_sandbox_session', { assistant: assistantId }, 'AI-Calling')
}


// ── Call transfers (ai_calling.ai_calling.transfer_admin) ────────────────────
const TRANSFER = 'ai_calling.ai_calling.transfer_admin.'
function transferCall(method, params = {}) {
  return callRpc(`${TRANSFER}${method}`, params, 'AI-Calling')
}

export function getTransferTeam() { return transferCall('get_transfer_team') }
export function saveTransferTeamMember({ user, number, available }, { clearAway = false } = {}) {
  return transferCall('save_transfer_team_member', { user, number, available: available ? 1 : 0, clear_away: clearAway ? 1 : 0 })
}
export function listTransferGroups() { return transferCall('list_transfer_groups') }
export function saveTransferGroup(data, name = null) {
  return transferCall('save_transfer_group', { data: JSON.stringify(data), name })
}
export function deleteTransferGroup(name) { return transferCall('delete_transfer_group', { name }) }
export function getHandoffHistory({ status = '', start = 0, limit = 50, search = '' } = {}) {
  return transferCall('get_handoff_history', { status, start, limit, search })
}
export function getTransferSummary(days = 7) { return transferCall('get_transfer_summary', { days }) }
export function getMyPhone() { return transferCall('get_my_phone') }
export function setMyPhone(number) { return transferCall('set_my_phone', { number }) }
// The signed-in person's own transfer availability (the account menu). awayUntil is a Date.
export function getMyAvailability() { return transferCall('get_my_availability') }
export function setMyAvailability({ available, awayUntil = null }) {
  return transferCall('set_my_availability', { available: available ? 1 : 0, away_until_utc: awayUntil ? awayUntil.toISOString() : '' })
}
