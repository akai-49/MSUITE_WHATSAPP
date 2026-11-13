<!--
  WhatsAppFlows — list page for WhatsApp Flows.

  Shows a grid view of automation/questionnaire flows, matching the visual
  richness of MSuite Social/Campaigns. Features metrics, filters, and cards.
-->
<template>
  <div class="wa-page">
    <!-- Header -->
    <PageHeader
      title="WhatsApp Flows"
      subtitle="Build interactive forms, surveys, and multi-step customer journeys"
    >
      <template #actions>
        <div class="flex items-center gap-3">
          <!-- View Toggle buttons -->
          <div class="view-toggle-btns">
            <button
              class="toggle-btn"
              :class="{ active: viewMode === 'grid' }"
              @click="setViewMode('grid')"
              title="Grid View"
              aria-label="Grid View"
            >
              <FeatherIcon name="grid" class="w-4 h-4" />
            </button>
            <button
              class="toggle-btn"
              :class="{ active: viewMode === 'list' }"
              @click="setViewMode('list')"
              title="List View"
              aria-label="List View"
            >
              <FeatherIcon name="list" class="w-4 h-4" />
            </button>
          </div>

          <button class="l-btn l-btn--primary" @click="$router.push({ name: 'WhatsAppFlowBuilder' })">
            <FeatherIcon name="plus" class="w-4 h-4" />
            <span>New Flow</span>
          </button>
        </div>
      </template>
    </PageHeader>

    <!-- Order Flow Automation Settings Card -->
    <div class="mb-6">
      <OrderFlowSettingsCard />
    </div>

    <!-- Stats Cards -->
    <section class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div class="cursor-pointer" @click="setStatusFilter('all')">
        <KpiCard
          label="Total"
          :value="store.flowMetrics.total"
          icon="git-branch"
          :class="{ 'ring-2 ring-[var(--brand)]': store.flowFilters.status === 'all' }"
        />
      </div>
      <div class="cursor-pointer" @click="setStatusFilter('Published')">
        <KpiCard
          label="Published"
          :value="store.flowMetrics.published"
          icon="check-circle"
          :class="{ 'ring-2 ring-emerald-500': store.flowFilters.status === 'Published' }"
        />
      </div>
      <div class="cursor-pointer" @click="setStatusFilter('Draft')">
        <KpiCard
          label="Draft"
          :value="store.flowMetrics.draft"
          icon="file-text"
          :class="{ 'ring-2 ring-amber-500': store.flowFilters.status === 'Draft' }"
        />
      </div>
      <div class="cursor-pointer" @click="setStatusFilter('Deprecated')">
        <KpiCard
          label="Deprecated"
          :value="store.flowMetrics.deprecated"
          icon="archive"
          :class="{ 'ring-2 ring-gray-500': store.flowFilters.status === 'Deprecated' }"
        />
      </div>
    </section>

    <!-- Loading state -->
    <div class="loading-state" v-if="store.flowsLoading">
      <div class="skeleton-grid">
        <div v-for="n in 3" :key="n" class="skeleton-card">
          <div class="skeleton skeleton-title"></div>
          <div class="skeleton skeleton-pill"></div>
          <div class="skeleton skeleton-desc"></div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!store.flows.length" class="p-8">
      <EmptyState
        :title="store.flowSearch ? 'No flows match your search' : 'No flows found'"
        :description="store.flowSearch ? 'Try a different search term or clear filters.' : 'Create your first interactive WhatsApp flow to automate user communication.'"
        variant="plain"
      >
        <template #actions>
          <button v-if="!store.flowSearch" class="l-btn l-btn--primary" @click="$router.push({ name: 'WhatsAppFlowBuilder' })">
            <FeatherIcon name="plus" class="w-4 h-4" />
            <span>Create Flow</span>
          </button>
        </template>
      </EmptyState>
    </div>

    <!-- Main Content Container with Bulk Action Bar -->
    <div v-else>
      <!-- Bulk action bar -->
      <div v-if="selectedNames.length" class="bulk-action-bar mb-4 rounded-xl border border-[var(--border)]">
        <span class="font-semibold text-[var(--ink-800)] dark:text-slate-200">{{ selectedNames.length }} selected</span>
        <button class="btn-bulk-delete" @click="showBulkDeleteConfirm = true" :disabled="isBulkDeleting">
          <FeatherIcon name="trash-2" class="w-3.5 h-3.5" />
          <span>{{ isBulkDeleting ? 'Deleting…' : 'Delete Selected' }}</span>
        </button>
        <button class="btn-bulk-cancel text-xs font-semibold px-2.5 py-1 rounded-md text-[var(--ink-500)] hover:text-[var(--ink-700)] dark:text-[var(--ink-400)] dark:hover:text-slate-200" @click="selectedNames = []">
          Cancel
        </button>
      </div>

      <!-- Card Grid View -->
      <div v-if="viewMode === 'grid'" class="cards-grid">
        <div v-for="flow in store.flows" :key="flow.name" class="flow-card relative" :class="{ 'ring-2 ring-[var(--brand)] bg-[var(--bg-sunken)]': selectedNames.includes(flow.name) }">
          <div class="flow-card-header">
            <div class="flex items-center gap-2">
              <input
                type="checkbox"
                class="rounded border-[var(--ink-200)] dark:border-slate-700 text-[var(--brand)] focus:ring-[var(--brand)] w-4 h-4 cursor-pointer"
                :checked="selectedNames.includes(flow.name)"
                @click.stop
                @change="toggleSelect(flow.name)"
              />
              <div class="flow-icon-wrapper">
                <FeatherIcon name="message-square" class="w-5 h-5 text-[var(--status-violet-fg)]" />
              </div>
            </div>
            <StatusPill :status="flow.status || 'Draft'" />
          </div>
          
          <div class="flow-card-body">
            <h3 class="flow-name" @click="editFlow(flow.name)">{{ flow.flow_name }}</h3>
            <span class="flow-id-lbl">{{ flow.flow_id || flow.name }}</span>
            <p class="flow-desc">{{ flow.description || 'Interactive WhatsApp form or customer conversation flow.' }}</p>
          </div>

          <div class="flow-card-footer">
            <div class="flow-meta">
              <span class="category-tag">{{ formatCategory(flow.category) }}</span>
              <span class="modified-time">{{ formatDate(flow.modified) }}</span>
            </div>
            <div class="flow-actions-wrapper">
              <button class="action-btn" @click="viewResponses(flow.name)" title="View Responses">
                <FeatherIcon name="inbox" class="w-3.5 h-3.5" />
              </button>
              <button class="action-btn" @click="editFlow(flow.name)" title="Edit Flow">
                <FeatherIcon name="edit-2" class="w-3.5 h-3.5" />
              </button>
              <button class="action-btn text-[var(--status-red-fg)]" @click="triggerDelete(flow)" title="Delete Flow">
                <FeatherIcon name="trash-2" class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Table List View -->
      <div v-else class="l-table-scroll">
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
              <th class="l-th">Flow Name</th>
              <th class="l-th">Flow ID</th>
              <th class="l-th">Category</th>
              <th class="l-th">Status</th>
              <th class="l-th">Last Updated</th>
              <th class="l-th actions-col"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="flow in store.flows" :key="flow.name" class="data-row" :class="{ 'bg-[var(--bg-sunken)]': selectedNames.includes(flow.name) }">
              <td class="checkbox-col" @click.stop>
                <input
                  type="checkbox"
                  class="rounded border-[var(--ink-200)] dark:border-slate-700 text-[var(--brand)] focus:ring-[var(--brand)]"
                  :checked="selectedNames.includes(flow.name)"
                  @change="toggleSelect(flow.name)"
                />
              </td>
              <td class="cell-title font-medium" @click="editFlow(flow.name)">
                <div class="cell-title-text">{{ flow.flow_name }}</div>
              </td>
              <td class="cell-flow-id">
                {{ flow.flow_id || flow.name }}
              </td>
              <td>
                <span class="category-tag">{{ formatCategory(flow.category) }}</span>
              </td>
              <td>
                <StatusPill :status="flow.status || 'Draft'" />
              </td>
              <td class="text-[var(--text-secondary)]">
                {{ formatDate(flow.modified) }}
              </td>
              <td class="actions-col">
                <div class="row-actions">
                  <button class="action-btn" @click="viewResponses(flow.name)" title="View Responses">
                    <FeatherIcon name="inbox" class="w-3.5 h-3.5" />
                  </button>
                  <button class="action-btn" @click="editFlow(flow.name)" title="Edit Flow">
                    <FeatherIcon name="edit-2" class="w-3.5 h-3.5" />
                  </button>
                  <button class="action-btn text-[var(--status-red-fg)]" @click="triggerDelete(flow)" title="Delete Flow">
                    <FeatherIcon name="trash-2" class="w-3.5 h-3.5" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Bulk Delete Confirmation -->
    <ConfirmDialog
      :open="showBulkDeleteConfirm"
      :title="`Delete ${selectedNames.length} Flow${selectedNames.length > 1 ? 's' : ''}?`"
      message="Are you sure you want to delete the selected WhatsApp flows? This will remove their configurations. This action cannot be undone."
      confirm="Delete Flows"
      cancel="Keep Flows"
      tone="danger"
      :busy="isBulkDeleting"
      busy-label="Deleting..."
      @confirm="confirmBulkDelete"
      @cancel="showBulkDeleteConfirm = false"
    />

    <!-- Delete Confirmation -->
    <ConfirmDialog
      :open="showDeleteConfirm"
      title="Delete Flow?"
      message="Are you sure you want to delete this WhatsApp flow? This will remove the flow configuration. This action cannot be undone."
      confirm="Delete Flow"
      cancel="Keep Flow"
      tone="danger"
      :busy="isDeleting"
      busy-label="Deleting..."
      @confirm="confirmDelete"
      @cancel="showDeleteConfirm = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { FeatherIcon } from 'frappe-ui'
import { useWhatsApp } from '@/modules/whatsapp/store/whatsapp'
import PageHeader from '@/shared/ui/PageHeader.vue'
import KpiCard from '@/shared/ui/KpiCard.vue'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'
import StatusPill from '@/shared/ui/StatusPill.vue'
import OrderFlowSettingsCard from '@/modules/ecommerce/components/OrderFlowSettingsCard.vue'

const store = useWhatsApp()
const router = useRouter()

const selectedNames = ref([])
const showBulkDeleteConfirm = ref(false)
const isBulkDeleting = ref(false)

const isAllSelected = computed(() => {
  const list = store.flows || []
  return list.length > 0 && list.every((f) => selectedNames.value.includes(f.name))
})

const isIndeterminate = computed(() => {
  const list = store.flows || []
  if (!list.length) return false
  const count = list.filter((f) => selectedNames.value.includes(f.name)).length
  return count > 0 && count < list.length
})

function toggleSelectAll() {
  const list = store.flows || []
  if (isAllSelected.value) {
    selectedNames.value = []
  } else {
    selectedNames.value = list.map((f) => f.name)
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

const viewMode = ref(localStorage.getItem('msuite_flow_view_mode') || 'grid')

function setViewMode(mode) {
  viewMode.value = mode
  localStorage.setItem('msuite_flow_view_mode', mode)
}

const showDeleteConfirm = ref(false)
const deleteTargetName = ref('')
const isDeleting = ref(false)

const statusFilters = [
  { value: 'all', label: 'All' },
  { value: 'Draft', label: 'Draft', dot: 'var(--ink-300)' },
  { value: 'Published', label: 'Published', dot: '#22c55e' },
  { value: 'Deprecated', label: 'Deprecated', dot: 'var(--ink-500)' }
]

async function fetchFlows() {
  await store.fetchFlows()
}

async function setStatusFilter(status) {
  store.flowFilters.status = status
  await fetchFlows()
}

function editFlow(name) {
  router.push({ name: 'WhatsAppFlowBuilder', query: { name } })
}

function viewResponses(name) {
  router.push({ name: 'WhatsAppFlowResponses', query: { flow: name } })
}

function triggerDelete(flow) {
  deleteTargetName.value = flow.name
  showDeleteConfirm.value = true
}

async function confirmDelete() {
  isDeleting.value = true
  try {
    await store.deleteFlow(deleteTargetName.value)
    showDeleteConfirm.value = false
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'Flow deleted.', indicator: 'green' })
    }
  } catch (e) {
    console.error('Failed to delete flow', e)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'Failed to delete flow.', indicator: 'red' })
    }
  } finally {
    isDeleting.value = false
  }
}

async function confirmBulkDelete() {
  if (!selectedNames.value.length) return
  isBulkDeleting.value = true
  try {
    const res = await store.bulkDeleteFlows(selectedNames.value)
    showBulkDeleteConfirm.value = false
    const count = res?.deleted?.length || selectedNames.value.length
    selectedNames.value = []
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({
        message: `Deleted ${count} flow${count > 1 ? 's' : ''} successfully.`,
        indicator: 'green',
      })
    }
  } catch (e) {
    console.error('Failed to bulk delete flows', e)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({
        message: e?.message || 'Failed to bulk delete flows.',
        indicator: 'red',
      })
    }
  } finally {
    isBulkDeleting.value = false
  }
}

// `category` is stored as a JSON array string (Meta Flows can carry more
// than one category) — parse it back into a readable label instead of
// dumping the raw JSON in the card.
function formatCategory(raw) {
  if (!raw) return 'OTHER'
  let list
  try {
    const parsed = JSON.parse(raw)
    list = Array.isArray(parsed) ? parsed : [parsed]
  } catch {
    list = [raw]
  }
  list = list.filter(Boolean)
  if (list.length === 0) return 'OTHER'
  if (list.length === 1) return list[0]
  return `${list[0]} +${list.length - 1}`
}

function formatDate(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

onMounted(async () => {
  store.flowSearch = ''
  await Promise.all([store.fetchFlowMetrics(), store.fetchFlows()])
})
</script>

<style scoped>
.wa-page {
  width: 100%;
  padding: 0;
  font-family: var(--font-stack, system-ui, -apple-system, sans-serif);
  color: var(--ink-900);
}

/* Header */
.wa-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
.wa-title { margin: 0; font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }
.wa-subtitle { margin: 4px 0 0; font-size: 14px; color: var(--ink-500); }
.wa-actions { display: flex; align-items: center; gap: 12px; }

.wa-search { position: relative; display: flex; align-items: center; }
.search-icon { position: absolute; left: 10px; width: 16px; height: 16px; color: var(--ink-300); pointer-events: none; }
.search-input { height: 38px; width: 220px; padding: 0 12px 0 34px; border: 1.5px solid var(--ink-100); border-radius: 10px; font-size: 13px; color: var(--ink-900); background: var(--surface-surface); outline: none; transition: border-color 0.15s; }
.search-input::placeholder { color: var(--ink-300); }
.search-input:focus { border-color: var(--brand); }

.btn-create { display: inline-flex; align-items: center; gap: 6px; height: 38px; padding: 0 18px; border: none; border-radius: 10px; background: var(--brand); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; transition: transform 0.08s, box-shadow 0.15s; box-shadow: var(--shadow-sm); }
.btn-create:hover { box-shadow: var(--shadow-md); }
.btn-create:active { transform: translateY(1px); }

/* Metrics Grid */
.metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 24px; }
.metric-card { display: flex; align-items: center; justify-content: space-between; padding: 20px; background: var(--surface-surface); border: 1px solid var(--ink-100); border-radius: 14px; transition: border-color 0.15s, box-shadow 0.2s, transform 0.15s; cursor: pointer; }
.metric-card:hover { border-color: var(--brand-lighter); box-shadow: 0 4px 20px rgba(0,0,0,0.06); transform: translateY(-1px); }
.metric-card.active { border-width: 1.5px; transform: translateY(-1px); }
.metric-card.card-total.active { border-color: var(--brand-500); background: rgba(52, 65, 156, 0.04); box-shadow: 0 4px 12px rgba(52, 65, 156, 0.08); }
.metric-card.card-published.active { border-color: var(--emerald-500); background: rgba(16, 185, 129, 0.04); box-shadow: 0 4px 12px rgba(16, 185, 129, 0.08); }
.metric-card.card-draft.active { border-color: var(--status-amber-fg); background: rgba(217, 119, 6, 0.04); box-shadow: 0 4px 12px rgba(217, 119, 6, 0.08); }
.metric-card.card-deprecated.active { border-color: var(--ink-500); background: rgba(100, 116, 139, 0.04); box-shadow: 0 4px 12px rgba(100, 116, 139, 0.08); }
.metric-info { display: flex; flex-direction: column; gap: 4px; }
.metric-label { font-size: 12px; font-weight: 500; color: var(--ink-500); text-transform: uppercase; letter-spacing: 0.03em; }
.metric-value { font-size: 24px; font-weight: 700; line-height: 1.2; }
.metric-icon-bg { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }

/* Cards Grid */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}
.flow-card {
  background: var(--surface-surface);
  border: 1px solid var(--ink-100);
  border-radius: 14px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 200px;
  transition: all 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}
.flow-card:hover {
  border-color: var(--brand-lighter);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
}
.flow-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.flow-icon-wrapper {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: var(--status-violet-bg);
  display: flex;
  align-items: center;
  justify-content: center;
}
.flow-card-body {
  margin-bottom: 16px;
  flex-grow: 1;
}
.flow-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--ink-900);
  margin: 0 0 2px;
  cursor: pointer;
  transition: color 0.15s;
}
.flow-name:hover {
  color: var(--brand);
}
.flow-id-lbl {
  font-family: monospace;
  font-size: 11px;
  color: var(--ink-300);
}
.flow-desc {
  font-size: 13px;
  color: var(--ink-500);
  margin: 10px 0 0;
  line-height: 1.5;
}

.flow-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid var(--ink-50);
  padding-top: 14px;
}
.flow-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.category-tag {
  font-size: var(--fs-2xs);
  font-weight: 600;
  padding: 2.5px 7px;
  border-radius: 5px;
  background: var(--status-violet-bg);
  color: var(--status-violet-fg);
}
.modified-time {
  font-size: 11px;
  color: var(--ink-300);
}
.flow-actions-wrapper {
  display: flex;
  align-items: center;
  gap: 4px;
}
.action-btn {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: var(--ink-500);
  cursor: pointer;
  transition: background 0.1s, color 0.1s;
}
.action-btn:hover {
  background: var(--ink-50);
  color: var(--ink-900);
}
.text-rose-600 {
  color: var(--status-red-fg);
}
.action-btn.text-rose-600:hover {
  background: var(--status-red-bg);
  color: var(--status-red-fg);
}

/* Status Pills */
.status-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.status-draft { background: var(--ink-50); color: var(--ink-600); }
.status-published { background: var(--status-green-bg); color: var(--status-green-fg); }
.status-deprecated { background: var(--ink-100); color: var(--ink-600); }

/* Empty state */
.empty-state-wrapper { text-align: center; padding: 80px 24px; }
.empty-icon { font-size: 48px; margin-bottom: 16px; color: var(--ink-300); }
.empty-title { font-size: 18px; font-weight: 600; color: var(--ink-900); margin: 0 0 8px; }
.empty-text { font-size: 14px; color: var(--ink-500); max-width: 440px; margin: 0 auto 24px; line-height: 1.6; }

/* Loading State skeleton */
.skeleton-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}
.skeleton-card {
  background: var(--surface-surface);
  border: 1px solid var(--ink-100);
  border-radius: 14px;
  padding: 20px;
  min-height: 200px;
}
.skeleton { border-radius: 6px; background: linear-gradient(90deg, var(--ink-50) 25%, var(--ink-100) 50%, var(--ink-50) 75%); background-size: 200% 100%; animation: shimmer 1.5s ease-in-out infinite; }
.skeleton-title { width: 140px; height: 16px; margin-bottom: 12px; }
.skeleton-pill { width: 60px; height: 22px; border-radius: 999px; margin-bottom: 20px; }
.skeleton-desc { width: 100%; height: 40px; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* Colors */
.text-slate-800 { color: var(--ink-800); }
.text-emerald-600 { color: var(--status-green-fg); }
.text-amber-600 { color: var(--status-amber-fg); }
.text-slate-500 { color: var(--ink-500); }
.bg-emerald-50 { background-color: var(--status-green-bg); }
.bg-amber-50 { background-color: var(--status-amber-bg); }
.bg-slate-50 { background-color: var(--ink-25); }
.bg-slate-100 { background-color: var(--ink-50); }

/* View Toggle styling */
.view-toggle-btns {
  display: flex;
  background: var(--ink-50);
  border-radius: 8px;
  padding: 2px;
  border: 1px solid var(--ink-100);
}
.toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--ink-500);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.toggle-btn:hover {
  color: var(--ink-900);
}
.toggle-btn.active {
  background: var(--surface-surface);
  color: var(--brand);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

/* List View Table styling */
.table-wrapper {
  background: var(--surface-surface);
  border: 1px solid var(--ink-100);
  border-radius: 14px;
  overflow-x: auto;
  overflow-y: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table th {
  padding: 12px 16px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-500);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--ink-100);
  background: var(--ink-25);
}
.data-table td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--ink-50);
  vertical-align: middle;
}
.data-row:last-child td {
  border-bottom: none;
}
.data-row:hover {
  background: var(--ink-25);
}
.cell-title {
  cursor: pointer;
}
.cell-title:hover .cell-title-text {
  color: var(--brand);
}
.cell-title-text {
  font-weight: 500;
  color: var(--ink-900);
  transition: color 0.15s;
}
.cell-flow-id {
  font-family: monospace;
  font-size: 11px;
  color: var(--ink-300);
}
.actions-col {
  width: 120px;
  text-align: right;
}
.row-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  justify-content: flex-end;
}

/* ── Bulk actions & pagination ───────────────────────── */
.bulk-action-bar { display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: var(--brand-lighter); border-bottom: 1px solid var(--border-base); font-size: 13px; font-weight: 500; color: var(--brand-color); }
.btn-bulk-delete { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border: 1px solid var(--state-danger-border); border-radius: 8px; background: var(--surface-surface); color: var(--state-danger); font-size: 12px; font-weight: 600; cursor: pointer; margin-left: auto; }
.btn-bulk-delete:hover { background: var(--state-danger-bg); }
.checkbox-col { width: 36px; text-align: center; }
</style>
