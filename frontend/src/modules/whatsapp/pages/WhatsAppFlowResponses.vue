<!--
  WhatsAppFlowResponses — list page for captured WhatsApp Flow submissions
  (nfm_reply payloads persisted by flow_response_service.py).

  Matches the WhatsAppBulkMessages.vue pattern: header, metrics, filters,
  table with an expandable detail row instead of a separate drawer.
-->
<template>
  <div class="wa-page">
    <!-- Header -->
    <PageHeader
      title="Flow Responses"
      :subtitle="flow ? `Submissions for ${flowLabel}` : 'Every submission captured across all WhatsApp Flows'"
      :back-to="{ name: 'WhatsAppFlows' }"
      back-label="Flows"
    />

    <!-- Stats Cards -->
    <section class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <KpiCard
        label="Total"
        :value="store.flowResponseMetrics.total"
        icon="inbox"
        clickable
        :active="store.flowResponseFilters.status === 'all'"
        @click="setStatusFilter('all')"
      />
      <KpiCard
        label="Awaiting Reply"
        :value="store.flowResponseMetrics.sent"
        icon="clock"
        clickable
        :active="store.flowResponseFilters.status === 'Sent'"
        @click="setStatusFilter('Sent')"
      />
      <KpiCard
        label="Completed"
        :value="store.flowResponseMetrics.completed"
        icon="check-circle"
        clickable
        :active="store.flowResponseFilters.status === 'Completed'"
        @click="setStatusFilter('Completed')"
      />
      <KpiCard
        label="Completion Rate"
        :value="`${store.flowResponseMetrics.completion_rate}%`"
        icon="percent"
      />
    </section>

    <!-- Loading state -->
    <div class="loading-state" v-if="store.flowResponsesLoading">
      <div v-for="n in 4" :key="n" class="skeleton-row">
        <div class="skeleton skeleton-title"></div>
        <div class="skeleton skeleton-pill"></div>
        <div class="skeleton skeleton-text"></div>
        <div class="skeleton skeleton-text-sm"></div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!store.flowResponses.length" class="p-8">
      <EmptyState
        title="No responses yet"
        description="Send a flow to a contact — replies land here automatically once they complete it."
        variant="plain"
      />
    </div>

    <!-- Table -->
    <div v-else class="l-table-scroll">
      <!-- Bulk action bar -->
      <div v-if="selectedNames.length" class="bulk-action-bar">
        <span class="font-semibold text-[var(--ink-800)] dark:text-slate-200">{{ selectedNames.length }} selected</span>
        <button class="btn-bulk-delete" @click="showBulkDeleteConfirm = true" :disabled="isBulkDeleting">
          <FeatherIcon name="trash-2" class="w-3.5 h-3.5" />
          <span>{{ isBulkDeleting ? 'Deleting…' : 'Delete Selected' }}</span>
        </button>
        <button class="btn-bulk-cancel text-xs font-semibold px-2.5 py-1 rounded-md text-[var(--ink-500)] hover:text-[var(--ink-700)] dark:text-[var(--ink-400)] dark:hover:text-slate-200" @click="selectedNames = []">
          Cancel
        </button>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th class="checkbox-col l-th">
              <input
                type="checkbox"
                class="rounded border-[var(--ink-200)] dark:border-slate-700 text-[var(--brand)] focus:ring-[var(--brand)]"
                :checked="isAllSelected"
                :indeterminate="isIndeterminate"
                @change="toggleSelectAll"
              />
            </th>
            <th class="l-th">Contact</th>
            <th v-if="!flow" class="l-th">Flow</th>
            <th class="l-th">Status</th>
            <th class="l-th">Sent</th>
            <th class="l-th">Completed</th>
            <th class="l-th actions-col"></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="resp in store.flowResponses" :key="resp.name">
            <tr class="data-row" :class="{ 'bg-[var(--bg-sunken)]': selectedNames.includes(resp.name) }" @click="toggleExpand(resp.name)">
              <td class="checkbox-col" @click.stop>
                <input
                  type="checkbox"
                  class="rounded border-[var(--ink-200)] dark:border-slate-700 text-[var(--brand)] focus:ring-[var(--brand)]"
                  :checked="selectedNames.includes(resp.name)"
                  @change="toggleSelect(resp.name)"
                />
              </td>
              <td class="cell-title font-medium">
                <div class="cell-title-text">{{ resp.contact_name || resp.contact_phone || 'Unknown contact' }}</div>
                <div class="cell-sub-text">{{ resp.contact_phone }}</div>
              </td>
              <td v-if="!flow">
                <span class="text-[var(--text-primary)]">{{ resp.flow_name_snapshot || '—' }}</span>
              </td>
              <td>
                <LStatusPill :kind="resp.status.toLowerCase() === 'completed' ? 'success' : resp.status" :label="resp.status" />
              </td>
              <td class="text-[var(--text-secondary)]">{{ formatDate(resp.sent_at) }}</td>
              <td class="text-[var(--text-secondary)]">{{ resp.completed_at ? formatDate(resp.completed_at) : '—' }}</td>
              <td class="actions-col">
                <div class="row-actions">
                  <button class="action-btn text-[var(--status-red-fg)]" @click.stop="triggerDelete(resp)" title="Delete">
                    <FeatherIcon name="trash-2" class="w-3.5 h-3.5" />
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="expandedName === resp.name" class="progress-detail-row">
              <td :colspan="flow ? 6 : 7">
                <div class="response-detail">
                  <Shimmer v-if="detailLoading" class="shm-pad" variant="rows" :count="3" />
                  <template v-else-if="detail && detail.fields && detail.fields.length">
                    <div v-for="f in detail.fields" :key="f.name" class="response-field-row">
                      <span class="response-field-label">{{ f.field_label || f.field_name }}</span>
                      <span class="response-field-value">{{ f.value || '—' }}</span>
                    </div>
                  </template>
                  <p v-else class="progress-detail-loading">No field responses recorded for this submission yet.</p>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- Bulk Delete Confirmation -->
    <ConfirmDialog
      :open="showBulkDeleteConfirm"
      :title="`Delete ${selectedNames.length} Response${selectedNames.length > 1 ? 's' : ''}?`"
      message="This permanently removes the selected captured submissions. This action cannot be undone."
      confirm="Delete Responses"
      cancel="Keep Responses"
      tone="danger"
      :busy="isBulkDeleting"
      busy-label="Deleting..."
      @confirm="confirmBulkDelete"
      @cancel="showBulkDeleteConfirm = false"
    />

    <!-- Delete Confirmation -->
    <ConfirmDialog
      :open="showDeleteConfirm"
      title="Delete Response?"
      message="This removes the captured submission permanently. This action cannot be undone."
      confirm="Delete Response"
      cancel="Keep Response"
      tone="danger"
      :busy="isDeleting"
      busy-label="Deleting..."
      @confirm="confirmDelete"
      @cancel="showDeleteConfirm = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { FeatherIcon, toast } from 'frappe-ui'
import { useWhatsApp } from '@/modules/whatsapp/store/whatsapp'
import PageHeader from '@/shared/ui/PageHeader.vue'
import LStatusPill from '@/shared/ui/LStatusPill.vue'
import KpiCard from '@/shared/ui/KpiCard.vue'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'
import { prettifyFrappeError } from '@/shared/utils/storeHelpers'

const props = defineProps({
  flow: { type: String, default: '' },
})

const store = useWhatsApp()
const router = useRouter()

const statusFilters = [
  { value: 'all', label: 'All' },
  { value: 'Sent', label: 'Awaiting Reply', dot: '#eab308' },
  { value: 'Completed', label: 'Completed', dot: '#22c55e' },
]

const expandedName = ref('')
const detail = ref(null)
const detailLoading = ref(false)

const selectedNames = ref([])
const showBulkDeleteConfirm = ref(false)
const isBulkDeleting = ref(false)

const isAllSelected = computed(() => {
  const list = store.flowResponses || []
  return list.length > 0 && list.every((r) => selectedNames.value.includes(r.name))
})

const isIndeterminate = computed(() => {
  const list = store.flowResponses || []
  if (!list.length) return false
  const count = list.filter((r) => selectedNames.value.includes(r.name)).length
  return count > 0 && count < list.length
})

function toggleSelectAll() {
  const list = store.flowResponses || []
  if (isAllSelected.value) {
    selectedNames.value = []
  } else {
    selectedNames.value = list.map((r) => r.name)
  }
}

function toggleSelect(name) {
  const idx = selectedNames.value.indexOf(name)
  if (idx > -1) {
    selectedNames.value.splice(idx, 1)
  } else {
    selectedNames.value.push(name)
  }
}

const showDeleteConfirm = ref(false)
const deleteTargetName = ref('')
const isDeleting = ref(false)

const flowLabel = computed(() => store.flowResponses[0]?.flow_name_snapshot || props.flow)

function goBack() {
  router.push({ name: 'WhatsAppFlows' })
}

async function fetchResponses() {
  store.flowResponseFilters.flow = props.flow || ''
  await store.fetchFlowResponses()
}

async function setStatusFilter(status) {
  store.flowResponseFilters.status = status
  await fetchResponses()
}

async function toggleExpand(name) {
  if (expandedName.value === name) {
    expandedName.value = ''
    detail.value = null
    return
  }
  expandedName.value = name
  detail.value = null
  detailLoading.value = true
  try {
    detail.value = await store.fetchFlowResponseDetail(name)
  } catch (e) {
    console.error('Failed to fetch flow response detail', e)
    toast.error(prettifyFrappeError(e) || 'Failed to fetch flow response detail')
  } finally {
    detailLoading.value = false
  }
}

function triggerDelete(resp) {
  deleteTargetName.value = resp.name
  showDeleteConfirm.value = true
}

async function confirmDelete() {
  isDeleting.value = true
  try {
    await store.deleteFlowResponse(deleteTargetName.value)
    if (expandedName.value === deleteTargetName.value) expandedName.value = ''
    showDeleteConfirm.value = false
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'Response deleted.', indicator: 'green' })
    }
  } catch (e) {
    console.error('Failed to delete flow response', e)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'Failed to delete response.', indicator: 'red' })
    }
  } finally {
    isDeleting.value = false
  }
}

async function confirmBulkDelete() {
  if (!selectedNames.value.length) return
  isBulkDeleting.value = true
  try {
    const res = await store.bulkDeleteFlowResponses(selectedNames.value)
    showBulkDeleteConfirm.value = false
    const count = res?.deleted?.length || selectedNames.value.length
    selectedNames.value = []
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({
        message: `Deleted ${count} response${count > 1 ? 's' : ''} successfully.`,
        indicator: 'green',
      })
    }
  } catch (e) {
    console.error('Failed to bulk delete flow responses', e)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({
        message: e?.message || 'Failed to bulk delete flow responses.',
        indicator: 'red',
      })
    }
  } finally {
    isBulkDeleting.value = false
  }
}

function formatDate(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  if (Number.isNaN(d.getTime())) return ''
  const dateStr = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  const timeStr = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  return `${dateStr} ${timeStr}`
}

watch(() => props.flow, fetchResponses)

onMounted(async () => {
  store.flowResponseFilters.flow = props.flow || ''
  await Promise.all([
    store.fetchFlowResponseMetrics(props.flow || ''),
    fetchResponses(),
  ])
})
</script>

<style scoped>
.wa-page {
  width: 100%;
  padding: 0;
  font-family: var(--font-stack, system-ui, -apple-system, sans-serif);
  color: var(--ink-900, #0f172a);
}

.back-link { display: inline-flex; align-items: center; gap: 6px; border: none; background: none; padding: 0; margin-bottom: 8px; font-size: 12.5px; font-weight: 500; color: var(--text-secondary); cursor: pointer; }
.back-link:hover { color: var(--brand-color); }

.wa-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
.wa-title { margin: 0; font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }
.wa-subtitle { margin: 4px 0 0; font-size: 14px; color: var(--text-secondary); }
.wa-actions { display: flex; align-items: center; gap: 12px; }

.wa-search { position: relative; display: flex; align-items: center; }
.search-icon { position: absolute; left: 10px; width: 16px; height: 16px; color: var(--text-tertiary); pointer-events: none; }
.search-input { height: 38px; width: 220px; padding: 0 12px 0 34px; border: 1.5px solid var(--border-base); border-radius: 10px; font-size: 13px; color: var(--text-primary); background: var(--surface-surface); outline: none; transition: border-color 0.15s; }
.search-input::placeholder { color: var(--text-tertiary); }
.search-input:focus { border-color: var(--brand-color); }

.loading-state { display: flex; flex-direction: column; gap: 12px; }
.skeleton-row { display: flex; align-items: center; gap: 16px; padding: 20px; background: var(--surface-surface); border: 1px solid var(--border-base); border-radius: 14px; }
.skeleton { border-radius: 6px; background: linear-gradient(90deg, var(--border-soft) 25%, var(--border-base) 50%, var(--border-soft) 75%); background-size: 200% 100%; animation: shimmer 1.5s ease-in-out infinite; }
.skeleton-title { width: 200px; height: 16px; }
.skeleton-pill { width: 60px; height: 22px; border-radius: 999px; }
.skeleton-text { width: 120px; height: 14px; }
.skeleton-text-sm { width: 80px; height: 14px; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

.empty-state-wrapper { text-align: center; padding: 80px 24px; }
.empty-icon { font-size: 48px; margin-bottom: 16px; color: var(--text-tertiary); }
.empty-title { font-size: 18px; font-weight: 600; color: var(--text-primary); margin: 0 0 8px; }
.empty-text { font-size: 14px; color: var(--text-secondary); max-width: 440px; margin: 0 auto 24px; line-height: 1.6; }

/* ── Bulk actions & pagination ───────────────────────── */
.bulk-action-bar { display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: var(--brand-lighter); border-bottom: 1px solid var(--border-base); font-size: 13px; font-weight: 500; color: var(--brand-color); }
.btn-bulk-delete { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border: 1px solid var(--state-danger-border); border-radius: 8px; background: var(--surface-surface); color: var(--state-danger); font-size: 12px; font-weight: 600; cursor: pointer; margin-left: auto; }
.btn-bulk-delete:hover { background: var(--state-danger-bg); }
.checkbox-col { width: 36px; text-align: center; }

.table-wrapper { background: var(--surface-surface); border: 1px solid var(--border-base); border-radius: 14px; overflow-x: auto;
  overflow-y: hidden; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { padding: 12px 16px; text-align: left; font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid var(--border-base); background: var(--surface-page); }
.data-table td { padding: 14px 16px; border-bottom: 1px solid var(--border-soft); vertical-align: middle; }
.data-row:last-child td { border-bottom: none; }
.data-row { cursor: pointer; }
.data-row:hover { background: var(--surface-page); }
.cell-title-text { font-weight: 500; color: var(--text-primary); }
.cell-sub-text { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; font-family: monospace; }

.actions-col { width: 60px; text-align: right; }
.row-actions { display: flex; align-items: center; gap: 4px; justify-content: flex-end; }
.action-btn { width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border: none; background: transparent; border-radius: 6px; color: var(--text-secondary); cursor: pointer; transition: background 0.1s, color 0.1s; }
.action-btn:hover { background: var(--border-soft); color: var(--text-primary); }
.text-rose-600 { color: var(--state-danger); }
.action-btn.text-rose-600:hover { background: var(--state-danger-bg); color: var(--state-danger); }

.progress-detail-row td { padding: 0; }
.response-detail { display: flex; flex-direction: column; gap: 10px; padding: 16px 20px; background: var(--surface-page); border-bottom: 1px solid var(--border-soft); }
.progress-detail-loading { font-size: 12px; color: var(--text-tertiary); }
.response-field-row { display: flex; gap: 12px; font-size: 13px; }
.response-field-label { min-width: 160px; font-weight: 600; color: var(--text-secondary); }
.response-field-value { color: var(--text-primary); word-break: break-word; }
</style>
