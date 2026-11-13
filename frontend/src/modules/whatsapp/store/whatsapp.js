import { defineStore } from 'pinia'
import { callRpc } from '@/services/_factory'

export const useWhatsApp = defineStore('whatsapp', {
  state: () => ({
    // Templates
    templates: [],
    templatesLoading: false,
    templateMetrics: { total: 0, approved: 0, pending: 0, rejected: 0, draft: 0 },
    templateFilters: {
      status: 'all',
      category: '',
      language: '',
      dateRange: '',
      customDates: { start: '', end: '' },
    },
    templateSearch: '',
    templateTotal: 0,
    templatePage: 1,
    templatePageSize: 25,
    templateSort: { field: 'modified', order: 'desc' },

    // Recipient Lists
    recipientLists: [],
    recipientListsLoading: false,
    recipientMetrics: { totalLists: 0, totalContacts: 0 },
    recipientFilters: {
      dateRange: '',
      customDates: { start: '', end: '' },
    },
    recipientSearch: '',

    // Bulk Messages
    bulkMessages: [],
    bulkMessagesLoading: false,
    bulkMetrics: { total: 0, draft: 0, scheduled: 0, inProgress: 0, completed: 0, partiallyFailed: 0 },
    bulkFilters: {
      status: 'all',
      template: '',
      dateRange: '',
      customDates: { start: '', end: '' },
    },
    bulkSearch: '',

    // Flows
    flows: [],
    flowsLoading: false,
    flowMetrics: { total: 0, published: 0, draft: 0, deprecated: 0 },
    flowFilters: {
      status: 'all',
    },
    flowSearch: '',

    // Flow Responses
    flowResponses: [],
    flowResponsesLoading: false,
    flowResponseMetrics: { total: 0, sent: 0, completed: 0, completion_rate: 0 },
    flowResponseFilters: {
      status: 'all',
      flow: '',
    },
    flowResponseSearch: '',

    // Dashboard
    dashboardLoading: false,
    dashboardError: null,
    dashboardPeriod: 'month',
    dashboardSummary: null,
    dashboardCategoryRollup: [],
    dashboardAccountStanding: null,
    dashboardDeliveryHealth: null,
    dashboardAivoFacts: null,
    dashboardPreviousPeriod: null,
    dashboardMetrics: {
      templates: 0,
      recipients: 0,
      activeBroadcasts: 0,
      messagesSent: 0,
      deliveryRate: 0,
      activeFlows: 0,
    },
    recentTemplates: [],
    recentBroadcasts: [],
  }),

  actions: {
    // ── Dashboard ───────────────────────────────────────────
    /**
     * Fetch WhatsApp Overview Dashboard metrics for the given period.
     * @param {string} [period='month'] - '7d', 'month', or 'qtr'
     * @returns {Promise<object|null>}
     */
    async fetchDashboardMetrics(period = 'month') {
      this.dashboardLoading = true
      this.dashboardError = null
      this.dashboardPeriod = period
      try {
        const res = await callRpc('msuite_whatsapp.api.v1.app.crud.get_dashboard_metrics', { period })
        if (res) {
          if (res.metrics) this.dashboardMetrics = res.metrics
          this.recentTemplates = res.recent_templates || []
          this.recentBroadcasts = res.recent_broadcasts || []
          this.dashboardSummary = res.summary || null
          this.dashboardCategoryRollup = res.category_rollup || []
          this.dashboardAccountStanding = res.account_standing || null
          this.dashboardDeliveryHealth = res.delivery_health || null
          this.dashboardAivoFacts = res.aivo_facts || null
          this.dashboardPreviousPeriod = res.previous_period || null
        }
        return res
      } catch (e) {
        console.error('[WhatsApp] Failed to fetch dashboard metrics', e)
        this.dashboardError = e?.message || 'Failed to load WhatsApp dashboard metrics'
        return null
      } finally {
        this.dashboardLoading = false
      }
    },

    // ── Templates ───────────────────────────────────────────
    async fetchTemplateMetrics() {
      try {
        const res = await callRpc('msuite_whatsapp.api.v1.app.crud.get_template_metrics')
        if (res) {
          this.templateMetrics = {
            total: res.total || 0,
            approved: res.approved || 0,
            pending: res.pending || 0,
            rejected: res.rejected || 0,
            draft: res.draft || 0
          }
        }
      } catch (e) {
        console.error('[WhatsApp] Failed to fetch template metrics', e)
      }
    },

    async fetchTemplates() {
      this.templatesLoading = true
      try {
        const filters = []
        if (this.templateFilters.status !== 'all') {
          filters.push(['status', '=', this.templateFilters.status])
        }
        if (this.templateFilters.category) {
          filters.push(['category', '=', this.templateFilters.category])
        }
        if (this.templateFilters.language) {
          filters.push(['language', 'like', `%${this.templateFilters.language}%`])
        }
        if (this.templateSearch.trim()) {
          filters.push(['template_name', 'like', `%${this.templateSearch.trim()}%`])
        }
        if (this.templateFilters.dateRange && this.templateFilters.dateRange !== 'custom') {
          const now = new Date()
          let from
          if (this.templateFilters.dateRange === 'today') from = new Date(now.getFullYear(), now.getMonth(), now.getDate())
          else if (this.templateFilters.dateRange === '7days') { from = new Date(now); from.setDate(from.getDate() - 7) }
          else if (this.templateFilters.dateRange === '30days') { from = new Date(now); from.setDate(from.getDate() - 30) }
          if (from) filters.push(['modified', '>=', from.toISOString().split('T')[0]])
        }
        if (this.templateFilters.dateRange === 'custom') {
          if (this.templateFilters.customDates.start) filters.push(['modified', '>=', this.templateFilters.customDates.start])
          if (this.templateFilters.customDates.end) filters.push(['modified', '<=', this.templateFilters.customDates.end])
        }

        const res = await callRpc('msuite_whatsapp.api.v1.app.crud.list_templates', {
          filters: JSON.stringify(filters),
          search: this.templateSearch.trim(),
          limit: this.templatePageSize,
          limit_start: (this.templatePage - 1) * this.templatePageSize,
          sort_by: this.templateSort.field,
          sort_order: this.templateSort.order,
        })
        this.templates = res?.rows || []
        this.templateTotal = res?.total || 0
      } catch (e) {
        console.error('[WhatsApp] Failed to fetch templates', e)
        this.templates = []
        this.templateTotal = 0
      } finally {
        this.templatesLoading = false
      }
    },

    async deleteTemplate(name, deleteFromWhatsapp = 1) {
      await callRpc('msuite_whatsapp.api.v1.app.crud.delete_whatsapp_template', {
        name,
        delete_from_whatsapp: deleteFromWhatsapp ? 1 : 0
      })
      await this.fetchTemplates()
      await this.fetchTemplateMetrics()
    },

    async bulkDeleteTemplates(names, deleteFromWhatsapp = 1) {
      const res = await callRpc('msuite_whatsapp.api.v1.app.crud.bulk_delete_templates', {
        names: JSON.stringify(names),
        delete_from_whatsapp: deleteFromWhatsapp ? 1 : 0
      })
      await this.fetchTemplates()
      await this.fetchTemplateMetrics()
      return res
    },

    async duplicateTemplate(name) {
      const res = await callRpc('msuite_whatsapp.api.v1.app.crud.duplicate_template', { name })
      await this.fetchTemplates()
      await this.fetchTemplateMetrics()
      return res
    },

    async syncTemplates() {
      try {
        const res = await callRpc('msuite_whatsapp.whatsapp.doctype.whatsapp_templates.template_sync.fetch')
        await this.fetchTemplates()
        await this.fetchTemplateMetrics()
        return res
      } catch (e) {
        console.error('[WhatsApp] Failed to sync templates', e)
        throw e
      }
    },

    async fetchTemplateDetail(name) {
      return await callRpc('msuite_whatsapp.api.v1.app.crud.get_whatsapp_template', { name })
    },

    // ── Recipient Lists ─────────────────────────────────────
    async fetchRecipientLists() {
      this.recipientListsLoading = true
      try {
        const res = await callRpc('msuite_whatsapp.api.v1.app.crud.list_recipient_lists', {
          search: this.recipientSearch.trim(),
          limit: 100
        })
        this.recipientLists = res || []
      } catch (e) {
        console.error('[WhatsApp] Failed to fetch recipient lists', e)
        this.recipientLists = []
      } finally {
        this.recipientListsLoading = false
      }
    },

    async fetchRecipientMetrics() {
      try {
        const res = await callRpc('msuite_whatsapp.api.v1.app.crud.get_recipient_metrics')
        if (res) {
          this.recipientMetrics = {
            totalLists: res.totalLists || 0,
            totalContacts: res.totalContacts || 0
          }
        }
      } catch (e) {
        console.error('[WhatsApp] Failed to fetch recipient metrics', e)
      }
    },

    async deleteRecipientList(name) {
      await callRpc('msuite_whatsapp.api.v1.app.crud.delete_recipient_list', { name })
      await this.fetchRecipientLists()
      await this.fetchRecipientMetrics()
    },

    // ── Bulk Messages ───────────────────────────────────────
    async fetchBulkMetrics() {
      try {
        const res = await callRpc('msuite_whatsapp.api.v1.app.crud.get_bulk_metrics')
        if (res) {
          this.bulkMetrics = {
            total: res.total || 0,
            draft: res.draft || 0,
            scheduled: res.scheduled || 0,
            inProgress: res.inProgress || 0,
            completed: res.completed || 0,
            partiallyFailed: res.partiallyFailed || 0
          }
        }
      } catch (e) {
        console.error('[WhatsApp] Failed to fetch bulk metrics', e)
      }
    },

    async fetchBulkMessages() {
      this.bulkMessagesLoading = true
      try {
        const filters = []
        if (this.bulkFilters.status !== 'all') {
          if (this.bulkFilters.status === 'In Progress') {
            filters.push(['status', 'in', ['Queued', 'In Progress']])
          } else {
            filters.push(['status', '=', this.bulkFilters.status])
          }
        }
        if (this.bulkFilters.template) {
          // Free-text input — partial match, not exact equality
          filters.push(['template', 'like', `%${this.bulkFilters.template.trim()}%`])
        }
        if (this.bulkFilters.dateRange && this.bulkFilters.dateRange !== 'custom') {
          const now = new Date()
          let from
          if (this.bulkFilters.dateRange === 'today') from = new Date(now.getFullYear(), now.getMonth(), now.getDate())
          else if (this.bulkFilters.dateRange === '7days') { from = new Date(now); from.setDate(from.getDate() - 7) }
          else if (this.bulkFilters.dateRange === '30days') { from = new Date(now); from.setDate(from.getDate() - 30) }
          if (from) filters.push(['modified', '>=', from.toISOString().split('T')[0]])
        }
        if (this.bulkFilters.dateRange === 'custom') {
          if (this.bulkFilters.customDates.start) filters.push(['modified', '>=', this.bulkFilters.customDates.start])
          if (this.bulkFilters.customDates.end) filters.push(['modified', '<=', this.bulkFilters.customDates.end])
        }

        const res = await callRpc('msuite_whatsapp.api.v1.app.crud.list_bulk_messages', {
          filters: JSON.stringify(filters),
          search: this.bulkSearch.trim(),
          limit: 100
        })
        this.bulkMessages = res || []
      } catch (e) {
        console.error('[WhatsApp] Failed to fetch bulk messages', e)
        this.bulkMessages = []
      } finally {
        this.bulkMessagesLoading = false
      }
    },

    async deleteBulkMessage(name) {
      await callRpc('msuite_whatsapp.api.v1.app.crud.delete_bulk_message', { name })
      await this.fetchBulkMessages()
      await this.fetchBulkMetrics()
    },

    async bulkDeleteBulkMessages(names) {
      const res = await callRpc('msuite_whatsapp.api.v1.app.crud.bulk_delete_bulk_messages', { names })
      await this.fetchBulkMessages()
      await this.fetchBulkMetrics()
      return res
    },

    async pauseBulkMessage(name) {
      await callRpc('msuite_whatsapp.api.v1.app.bulk_messaging.pause', { name })
      await this.fetchBulkMessages()
    },

    async resumeBulkMessage(name) {
      await callRpc('msuite_whatsapp.api.v1.app.bulk_messaging.resume', { name })
      await this.fetchBulkMessages()
    },

    async cancelBulkMessage(name) {
      await callRpc('msuite_whatsapp.api.v1.app.bulk_messaging.cancel', { name })
      await this.fetchBulkMessages()
    },

    async retryBulkMessage(name) {
      const res = await callRpc('msuite_whatsapp.api.v1.app.bulk_messaging.retry_failed', { name })
      await this.fetchBulkMessages()
      return res?.requeued || 0
    },

    async fetchBulkProgress(name) {
      return await callRpc('msuite_whatsapp.api.v1.app.bulk_messaging.get_progress', { name })
    },

    // ── Flows ───────────────────────────────────────────────
    async fetchFlowMetrics() {
      try {
        const res = await callRpc('msuite_whatsapp.api.v1.app.crud.get_flow_metrics')
        if (res) {
          this.flowMetrics = {
            total: res.total || 0,
            published: res.published || 0,
            draft: res.draft || 0,
            deprecated: res.deprecated || 0
          }
        }
      } catch (e) {
        console.error('[WhatsApp] Failed to fetch flow metrics', e)
      }
    },

    async fetchFlows() {
      this.flowsLoading = true
      try {
        const filters = []
        if (this.flowFilters.status !== 'all') {
          filters.push(['status', '=', this.flowFilters.status])
        }

        const res = await callRpc('msuite_whatsapp.api.v1.app.crud.list_flows', {
          filters: JSON.stringify(filters),
          search: this.flowSearch.trim(),
          limit: 100
        })
        this.flows = res || []
      } catch (e) {
        console.error('[WhatsApp] Failed to fetch flows', e)
        this.flows = []
      } finally {
        this.flowsLoading = false
      }
    },

    async deleteFlow(name) {
      await callRpc('msuite_whatsapp.api.v1.app.crud.delete_flow', { name })
      await this.fetchFlows()
      await this.fetchFlowMetrics()
    },

    async bulkDeleteFlows(names) {
      const res = await callRpc('msuite_whatsapp.api.v1.app.crud.bulk_delete_flows', { names })
      await this.fetchFlows()
      await this.fetchFlowMetrics()
      return res
    },

    // ── Flow Responses ──────────────────────────────────────
    async fetchFlowResponseMetrics(flow = '') {
      try {
        const res = await callRpc('msuite_whatsapp.api.v1.app.crud.get_flow_response_metrics', { flow })
        if (res) {
          this.flowResponseMetrics = {
            total: res.total || 0,
            sent: res.sent || 0,
            completed: res.completed || 0,
            completion_rate: res.completion_rate || 0,
          }
        }
      } catch (e) {
        console.error('[WhatsApp] Failed to fetch flow response metrics', e)
      }
    },

    async fetchFlowResponses() {
      this.flowResponsesLoading = true
      try {
        const filters = []
        if (this.flowResponseFilters.status !== 'all') {
          filters.push(['status', '=', this.flowResponseFilters.status])
        }
        if (this.flowResponseSearch.trim()) {
          filters.push(['contact_phone', 'like', `%${this.flowResponseSearch.trim()}%`])
        }

        const res = await callRpc('msuite_whatsapp.api.v1.app.crud.list_flow_responses', {
          flow: this.flowResponseFilters.flow || '',
          filters: JSON.stringify(filters),
          limit: 100,
        })
        this.flowResponses = res || []
      } catch (e) {
        console.error('[WhatsApp] Failed to fetch flow responses', e)
        this.flowResponses = []
      } finally {
        this.flowResponsesLoading = false
      }
    },

    async fetchFlowResponseDetail(name) {
      return await callRpc('msuite_whatsapp.api.v1.app.crud.get_flow_response', { name })
    },

    async deleteFlowResponse(name) {
      await callRpc('msuite_whatsapp.api.v1.app.crud.delete_flow_response', { name })
      await this.fetchFlowResponses()
      await this.fetchFlowResponseMetrics(this.flowResponseFilters.flow)
    },

    async bulkDeleteFlowResponses(names) {
      const res = await callRpc('msuite_whatsapp.api.v1.app.crud.bulk_delete_flow_responses', { names })
      await this.fetchFlowResponses()
      await this.fetchFlowResponseMetrics(this.flowResponseFilters.flow)
      return res
    },
  }
})
