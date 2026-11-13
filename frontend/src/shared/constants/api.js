/**
 * RPC base prefixes — single source of truth for every whitelisted
 * Frappe method the SPA calls.
 *
 * Why one file:
 *   • Backend module renames (e.g. Campaign → Marketing Campaign) used
 *     to touch every service file. Now they touch one line here.
 *   • Grep "RPC.adComposer" finds every call site at once.
 *   • Tooling (lints, codemods) can validate paths against this map.
 *
 * Each value ends with a trailing dot — services concatenate the
 * specific method onto it (e.g. `${RPC.adComposer}create_or_load`).
 */
export const RPC = Object.freeze({
  // ── Inbox ────────────────────────────────────────────────────────────
  inbox:             'msuite_inbox.inbox.api.v1.conversation.',
  engage:            'msuite_inbox.inbox.api.v1.engage.',
  quickReply:        'msuite_inbox.inbox.api.v1.quick_reply.',
  richMedia:         'msuite_inbox.inbox.api.v1.rich_media.',
  instagramMessaging: 'msuite_inbox.inbox.api.v1.instagram.',
  facebookMessenger:  'msuite_inbox.inbox.api.v1.facebook_messenger.',


  // ── Ads ──────────────────────────────────────────────────────────────
  adComposer:        'msuite_ads.ads.api.v1.composer.',
  adCampaignGroup:   'msuite_ads.ads.api.v1.group.',
  adsDashboard:      'msuite_ads.ads.dashboard.',
  adsInsights:       'msuite_ads.ads.domain.insights.query.',
  adAudiences:       'msuite_ads.api.v1.ads.audiences.',
  adCreativeEditor:  'msuite_ads.ads.api.v1.creative_editor.',
  leadGenFormEditor: 'msuite_ads.ads.api.v1.lead_gen_form_editor.',
  creativeLibrary:   'msuite_ads.ads.domain.creatives.library.',
  mediaLibrary:      'msuite_core.api.v1.app.media_library.',

  // ── Campaign ─────────────────────────────────────────────────────────
  campaign:          'msuite_campaigns.campaign.api.v1.composer.',
  campaignLinks:     'msuite_campaigns.campaign.api.v1.links.',
  campaignRunner:    'msuite_campaigns.campaign.api.runner.',
  campaignRollup:    'msuite_campaigns.campaign.rollup.',
  campaignDashboard: 'msuite_campaigns.campaign.dashboard.',
  campaignCalendar:  'msuite_campaigns.campaign.api.v1.calendar.',
  audience:          'msuite_campaigns.audience.api.v1.audience.',
  dispatchHub:       'msuite_campaigns.dispatch.api.v1.campaign.',
  sms:               'msuite_sms.sms.api.templates.',

  // ── Social ───────────────────────────────────────────────────────────
  socialComposer:    'msuite_social.social_post.api.v1.composer.',
  socialDashboard:   'msuite_social.social_post.dashboard.',
  socialDoctype:     'msuite_social.social_post.doctype.social_post.social_post.',
  socialInsights:    'msuite_social.social_post.insights.query.',
  socialInsightsSync: 'msuite_social.social_post.insights.sync.',
  socialMentions:    'msuite_inbox.inbox.api.v1.mentions.',
  socialCollaborations: 'msuite_inbox.inbox.api.v1.ig_collab_invites.',

  // ── Performance ──────────────────────────────────────────────────────
  performance:       'msuite_campaigns.performance.api.',

  // ── WhatsApp Cloud (calling) ─────────────────────────────────────────
  whatsappCalls:     'msuite_whatsapp.api.v1.app.calls.',

  // ── CRM (Frappe CRM — separate installed app, not msuite_workspace) ───
  // We call into `crm`'s own whitelisted methods for the handful of
  // things its API does that a generic frappe.client list/get/set
  // doesn't (linked deals, the Lead/Deal activity timeline). Everything
  // else (list/get/create/update CRM Lead/Deal/Contact) goes through
  // RPC.frappeClient below — no msuite_workspace backend code needed.
  crmContact:        'crm.api.contact.',
  crmActivities:     'crm.api.activities.',
  crmDealCreate:     'custom_crm.api.v1.deal.',
  crmComment:        'crm.api.comment.',
  crmSession:        'crm.api.session.',
  // Doc-level whitelisted methods that live on the CRM Lead controller
  // (convert_to_deal) rather than under crm.api.*.
  crmLeadDoc:        'crm.fcrm.doctype.crm_lead.crm_lead.',

  // ── GetSeen ──────────────────────────────────────────────────────────
  getseen:           'aeo_checker_app.api.v1.',

  // ── Home & Tasks ─────────────────────────────────────────────────────
  home:              'msuite_core.api.v1.app.home.',
  homeOverview:      'msuite_core.api.v1.app.home_overview.',
  tasks:             'msuite_core.api.v1.app.tasks.',

  // ── Frappe built-ins ─────────────────────────────────────────────────
  // Rare — only when reaching into Frappe's generic client API
  // (Version log, get_list bypass for one-offs).
  frappeClient:      'frappe.client.',
})

/**
 * Bare upload endpoint — multipart/form-data, can't go through
 * frappeRequest. Used by inbox/composer attachment flows.
 */
export const FRAPPE_UPLOAD_URL = '/api/method/upload_file'
