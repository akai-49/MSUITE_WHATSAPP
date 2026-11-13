<!--
  WhatsAppRecipients — list page for Recipient Lists.

  Since WhatsApp Recipient is a child table, this page manages
  WhatsApp Recipient List as the primary entity.
-->
<template>
  <div class="wa-page">
    <!-- Header -->
    <PageHeader
      title="Recipients"
      subtitle="Manage WhatsApp recipient lists and audience segments"
    >
      <template #actions>
        <button class="l-btn l-btn--primary" @click="$router.push({ name: 'WhatsAppRecipientCreate' })">
          <FeatherIcon name="plus" class="w-4 h-4" />
          <span>New List</span>
        </button>
      </template>
    </PageHeader>

    <!-- Stats -->
    <section class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      <KpiCard
        label="Total Lists"
        :value="store.recipientMetrics.totalLists"
        icon="list"
      />
      <KpiCard
        label="Total Contacts"
        :value="store.recipientMetrics.totalContacts"
        icon="users"
      />
    </section>



    <!-- Loading -->
    <Shimmer v-if="store.recipientListsLoading" variant="rows" :count="5" />

    <!-- Empty State -->
    <div v-else-if="!store.recipientLists.length" class="p-8">
      <EmptyState
        :title="store.recipientSearch ? 'No lists match your search' : 'No recipient lists found'"
        :description="store.recipientSearch ? 'Try a different search term.' : 'Create your first recipient list to start sending WhatsApp messages to groups of people.'"
        variant="plain"
      >
        <template #actions>
          <button v-if="!store.recipientSearch" class="l-btn l-btn--primary" @click="$router.push({ name: 'WhatsAppRecipientCreate' })">
            <FeatherIcon name="plus" class="w-4 h-4" />
            <span>Create List</span>
          </button>
        </template>
      </EmptyState>
    </div>

    <!-- Table + bulk actions -->
    <div v-else>
      <div v-if="selectedNames.length" class="bulk-bar">
        <span>{{ selectedNames.length }} selected</span>
        <button class="l-btn l-btn--secondary l-btn--sm" @click="selectedNames = []">Clear</button>
        <button class="l-btn l-btn--danger l-btn--sm" @click="triggerBulkDelete">
          <FeatherIcon name="trash-2" class="w-3.5 h-3.5" /> Delete Selected
        </button>
      </div>
      <div class="l-table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th class="checkbox-col l-th"><input type="checkbox" :checked="allSelected" @change="toggleSelectAll" /></th>
            <th class="l-th">List Name</th>
            <th class="l-th">Description</th>
            <th class="l-th">Created By</th>
            <th class="l-th">Created</th>
            <th class="l-th">Last Updated</th>
            <th class="l-th actions-col"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="list in store.recipientLists" :key="list.name" class="data-row">
            <td class="checkbox-col">
              <input type="checkbox" :checked="selectedNames.includes(list.name)" @change="toggleSelect(list.name)" />
            </td>
            <td class="cell-title font-medium" @click="viewList(list.name)">
              <div class="cell-title-text">{{ list.list_name || list.name }}</div>
            </td>
            <td class="text-[var(--text-secondary)] cell-desc">{{ list.description || '—' }}</td>
            <td class="text-[var(--text-secondary)]">{{ list.owner || '—' }}</td>
            <td class="text-[var(--text-secondary)]">{{ formatDate(list.creation) }}</td>
            <td class="text-[var(--text-secondary)]">{{ formatDate(list.modified) }}</td>
            <td class="actions-col">
              <div class="row-actions">
                <button class="action-btn" @click="viewList(list.name)" title="View">
                  <FeatherIcon name="eye" class="w-3.5 h-3.5" />
                </button>
                <button class="action-btn" @click="triggerRename(list)" title="Rename">
                  <FeatherIcon name="edit-2" class="w-3.5 h-3.5" />
                </button>
                <button class="action-btn text-[var(--status-red-fg)]" @click="triggerDelete(list)" title="Delete">
                  <FeatherIcon name="trash-2" class="w-3.5 h-3.5" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </div>

    <!-- New List Modal removed, now navigates to create route -->

    <!-- Rename Modal -->
    <Teleport to="body">
      <div v-if="showRename" class="modal-overlay" @click.self="showRename = false">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Rename List</h3>
            <button class="modal-close" @click="showRename = false">
              <FeatherIcon name="x" class="w-4 h-4" />
            </button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label class="form-label">List Name</label>
              <input type="text" class="form-control" v-model="renameValue" @keyup.enter="confirmRename" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn-secondary" @click="showRename = false">Cancel</button>
            <button class="btn-create" :disabled="!renameValue.trim() || isRenaming" @click="confirmRename">
              {{ isRenaming ? 'Renaming…' : 'Rename' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Delete Confirmation -->
    <ConfirmDialog
      :open="showDeleteConfirm"
      title="Delete Recipient List?"
      message="Are you sure? All recipients in this list will be removed. This action cannot be undone."
      confirm="Delete List"
      cancel="Keep List"
      tone="danger"
      :busy="isDeleting"
      busy-label="Deleting..."
      @confirm="confirmDelete"
      @cancel="showDeleteConfirm = false"
    />

    <!-- Bulk Delete Confirmation -->
    <ConfirmDialog
      :open="showBulkDeleteConfirm"
      title="Delete Selected Lists?"
      :message="`Are you sure you want to delete ${selectedNames.length} recipient list(s)? All recipients in them will be removed. This cannot be undone.`"
      confirm="Delete Lists"
      cancel="Keep Lists"
      tone="danger"
      :busy="isBulkDeleting"
      busy-label="Deleting..."
      @confirm="confirmBulkDelete"
      @cancel="showBulkDeleteConfirm = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { FeatherIcon, frappeRequest, toast } from 'frappe-ui'
import { useWhatsApp } from '@/modules/whatsapp/store/whatsapp'
import PageHeader from '@/shared/ui/PageHeader.vue'
import KpiCard from '@/shared/ui/KpiCard.vue'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'
import { prettifyFrappeError } from '@/shared/utils/storeHelpers'

const store = useWhatsApp()
const router = useRouter()

const showDeleteConfirm = ref(false)
const deleteTargetName = ref('')
const isDeleting = ref(false)

// ── Selection + bulk delete ───────────────────────────────────────────
const selectedNames = ref([])
const showBulkDeleteConfirm = ref(false)
const isBulkDeleting = ref(false)

const allSelected = computed(() =>
  store.recipientLists.length > 0 && selectedNames.value.length === store.recipientLists.length
)

function toggleSelect(name) {
  const idx = selectedNames.value.indexOf(name)
  if (idx >= 0) selectedNames.value.splice(idx, 1)
  else selectedNames.value.push(name)
}

function toggleSelectAll() {
  selectedNames.value = allSelected.value ? [] : store.recipientLists.map((l) => l.name)
}

function triggerBulkDelete() {
  showBulkDeleteConfirm.value = true
}

async function confirmBulkDelete() {
  isBulkDeleting.value = true
  try {
    const res = await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.bulk_delete_recipient_lists',
      method: 'POST',
      params: { names: JSON.stringify(selectedNames.value) },
    })
    selectedNames.value = []
    showBulkDeleteConfirm.value = false
    await Promise.all([store.fetchRecipientLists(), store.fetchRecipientMetrics()])
    if (window.frappe?.show_alert) {
      const failed = res.failed?.length || 0
      window.frappe.show_alert({
        message: `Deleted ${res.deleted.length} list(s)${failed ? `, ${failed} failed` : ''}.`,
        indicator: failed ? 'orange' : 'green',
      })
    }
  } catch (e) {
    console.error('Failed to bulk delete lists', e)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'Failed to delete selected lists.', indicator: 'red' })
    }
  } finally {
    isBulkDeleting.value = false
  }
}

// ── Rename ──────────────────────────────────────────────────────────────
const showRename = ref(false)
const renameTargetName = ref('')
const renameValue = ref('')
const isRenaming = ref(false)

function triggerRename(list) {
  renameTargetName.value = list.name
  renameValue.value = list.list_name || list.name
  showRename.value = true
}

async function confirmRename() {
  if (!renameValue.value.trim()) return
  isRenaming.value = true
  try {
    await frappeRequest({
      url: '/api/method/msuite_whatsapp.api.v1.app.crud.rename_recipient_list',
      method: 'POST',
      params: { name: renameTargetName.value, new_name: renameValue.value.trim() },
    })
    showRename.value = false
    await store.fetchRecipientLists()
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'List renamed.', indicator: 'green' })
    }
  } catch (e) {
    console.error('Failed to rename list', e)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: e?.messages?.[0] || 'Failed to rename list.', indicator: 'red' })
    }
  } finally {
    isRenaming.value = false
  }
}



async function fetchRecipientLists() {
  await store.fetchRecipientLists()
}

function viewList(name) {
  router.push({ name: 'WhatsAppRecipientDetail', params: { id: name } })
}

// createNewList removed, handled by new full page editor

function triggerDelete(list) {
  deleteTargetName.value = list.name
  showDeleteConfirm.value = true
}

async function confirmDelete() {
  isDeleting.value = true
  try {
    await store.deleteRecipientList(deleteTargetName.value)
    showDeleteConfirm.value = false
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'List deleted.', indicator: 'green' })
    }
  } catch (e) {
    console.error('Failed to delete list', e)
    toast.error(prettifyFrappeError(e) || 'Failed to delete list')
  } finally {
    isDeleting.value = false
  }
}

function formatDate(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

onMounted(async () => {
  await Promise.all([store.fetchRecipientMetrics(), store.fetchRecipientLists()])
})
</script>

<style scoped>
.wa-page { width: 100%; padding: 0; font-family: var(--font-stack, system-ui, -apple-system, sans-serif); color: var(--ink-900, #0f172a); }

.wa-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
.wa-title { margin: 0; font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }
.wa-subtitle { margin: 4px 0 0; font-size: 14px; color: var(--ink-500); }
.wa-actions { display: flex; align-items: center; gap: 12px; }
.wa-search { position: relative; display: flex; align-items: center; }
.search-icon { position: absolute; left: 10px; width: 16px; height: 16px; color: var(--ink-300); pointer-events: none; }
.search-input { height: 38px; width: 200px; padding: 0 12px 0 34px; border: 1.5px solid var(--ink-100); border-radius: 10px; font-size: 13px; color: var(--ink-900); background: var(--bg-surface); outline: none; transition: border-color 0.15s; }
.search-input::placeholder { color: var(--ink-300); }
.search-input:focus { border-color: var(--brand); }
.btn-secondary { display: inline-flex; align-items: center; gap: 6px; height: 38px; padding: 0 16px; border: 1.5px solid var(--ink-100); border-radius: 10px; background: var(--bg-surface); font-size: 13px; font-weight: 600; color: var(--ink-600); cursor: pointer; }
.btn-secondary:hover { border-color: var(--ink-200); }
.btn-sm { height: 34px; font-size: 12px; }
.btn-create { display: inline-flex; align-items: center; gap: 6px; height: 38px; padding: 0 18px; border: none; border-radius: 10px; background: var(--brand); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; box-shadow: var(--shadow-sm); }
.btn-create:hover { box-shadow: var(--shadow-md); }
.btn-create:disabled { opacity: 0.5; cursor: not-allowed; }

.metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 24px; }
.metric-card { display: flex; align-items: center; justify-content: space-between; padding: 20px; background: var(--bg-surface); border: 1px solid var(--ink-100); border-radius: 14px; transition: border-color 0.15s, box-shadow 0.2s; }
.metric-card:hover { border-color: var(--brand-100); box-shadow: 0 4px 20px rgba(0,0,0,0.06); }
.metric-info { display: flex; flex-direction: column; gap: 4px; }
.metric-label { font-size: 12px; font-weight: 500; color: var(--ink-500); text-transform: uppercase; letter-spacing: 0.03em; }
.metric-value { font-size: 24px; font-weight: 700; line-height: 1.2; }
.metric-icon-bg { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }

/* Upload zone */
.upload-zone { margin-bottom: 20px; }
.upload-drop-area { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 40px; border: 2px dashed var(--ink-100); border-radius: 14px; background: var(--ink-25); cursor: pointer; transition: border-color 0.15s, background 0.15s; }
.upload-drop-area:hover { border-color: var(--brand-100); background: var(--status-violet-bg); }
.upload-title { font-size: 16px; font-weight: 600; color: var(--ink-900); margin: 8px 0 2px; }
.upload-desc { font-size: 13px; color: var(--ink-500); margin: 0; }
.upload-formats { font-size: 11px; color: var(--ink-300); margin: 0 0 8px; }
.hidden-file-input { display: none; }
.upload-error { color: var(--status-red-fg); font-size: 12px; margin: 8px 0 0; }

/* Loading, empty, table — same as WhatsAppTemplates */
.loading-state { display: flex; flex-direction: column; gap: 12px; }
.skeleton-row { display: flex; align-items: center; gap: 16px; padding: 20px; background: var(--bg-surface); border: 1px solid var(--ink-100); border-radius: 14px; }
.skeleton { border-radius: 6px; background: linear-gradient(90deg, var(--ink-50) 25%, var(--ink-100) 50%, var(--ink-50) 75%); background-size: 200% 100%; animation: shimmer 1.5s ease-in-out infinite; }
.skeleton-title { width: 200px; height: 16px; }
.skeleton-text { width: 120px; height: 14px; }
.skeleton-text-sm { width: 80px; height: 14px; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

.empty-state-wrapper { text-align: center; padding: 80px 24px; }
.empty-icon { font-size: 48px; margin-bottom: 16px; color: var(--ink-300); }
.empty-title { font-size: 18px; font-weight: 600; color: var(--ink-900); margin: 0 0 8px; }
.empty-text { font-size: 14px; color: var(--ink-500); max-width: 440px; margin: 0 auto 24px; line-height: 1.6; }
.empty-actions { display: flex; justify-content: center; gap: 12px; }

.table-wrapper { background: var(--bg-surface); border: 1px solid var(--ink-100); border-radius: 14px; overflow-x: auto;
  overflow-y: hidden; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { padding: 12px 16px; text-align: left; font-size: 11px; font-weight: 600; color: var(--ink-500); text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid var(--ink-100); background: var(--ink-25); }
.data-table td { padding: 14px 16px; border-bottom: 1px solid var(--ink-50); vertical-align: middle; }
.data-row:last-child td { border-bottom: none; }
.data-row:hover { background: var(--ink-25); }
.cell-title { cursor: pointer; }
.cell-title:hover .cell-title-text { color: var(--brand); }
.cell-title-text { font-weight: 500; color: var(--ink-900); transition: color 0.15s; }
.cell-desc { max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.actions-col { width: 100px; text-align: right; }
.checkbox-col { width: 36px; text-align: center; }
.row-actions { display: flex; align-items: center; gap: 4px; justify-content: flex-end; }
.action-btn { width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border: none; background: transparent; border-radius: 6px; color: var(--ink-500); cursor: pointer; transition: background 0.1s; }
.action-btn:hover { background: var(--ink-50); color: var(--ink-900); }
.text-rose-600 { color: var(--status-red-fg); }

/* Bulk action bar */
.bulk-bar { display: flex; align-items: center; gap: 12px; padding: 12px 16px; margin-bottom: 12px; background: var(--status-blue-bg); border: 1px solid var(--status-blue-bg); border-radius: 10px; font-size: 13px; font-weight: 500; color: var(--status-blue-fg); }
.btn-danger { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 14px; border: none; border-radius: 8px; background: var(--status-red-fg); color: #fff; font-size: 12px; font-weight: 600; cursor: pointer; margin-left: auto; }
.btn-danger:hover { background: var(--status-red-fg); }

/* Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100; display: flex; align-items: center; justify-content: center; }
.modal-card { background: var(--bg-surface); border-radius: 18px; box-shadow: 0 20px 60px rgba(0,0,0,0.15); width: 480px; max-width: 90vw; overflow: hidden; animation: modalIn 0.2s cubic-bezier(0.16,1,0.3,1); }
@keyframes modalIn { from { opacity: 0; transform: translateY(12px) scale(0.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
.modal-header { display: flex; align-items: center; justify-content: space-between; padding: 20px 24px 16px; border-bottom: 1px solid var(--ink-50); }
.modal-header h3 { margin: 0; font-size: 17px; font-weight: 600; }
.modal-close { width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border: none; background: transparent; border-radius: 8px; color: var(--ink-500); cursor: pointer; }
.modal-close:hover { background: var(--ink-50); }
.modal-body { padding: 20px 24px; }
.modal-footer { display: flex; justify-content: flex-end; gap: 10px; padding: 16px 24px; border-top: 1px solid var(--ink-50); }
.form-group { margin-bottom: 18px; }
.form-label { display: block; font-size: 12px; font-weight: 600; color: var(--ink-600); text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 6px; }
.form-control { width: 100%; height: 40px; padding: 0 14px; border: 1.5px solid var(--ink-100); border-radius: 10px; font-size: 14px; color: var(--ink-900); background: var(--bg-surface); outline: none; transition: border-color 0.15s; box-sizing: border-box; }
.form-control:focus { border-color: var(--brand); }
.form-textarea { height: auto; padding: 12px 14px; resize: vertical; }
</style>
