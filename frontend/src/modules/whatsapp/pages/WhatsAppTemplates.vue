<!--
  WhatsAppTemplates — list page for WhatsApp Templates.

  Matches the Campaigns/AdsManager pattern: header, stats, filter pills,
  advanced filters, search, table with row actions, empty state.
-->
<template>
  <div class="wa-page">
    <!-- Header -->
    <PageHeader
      title="Templates"
      subtitle="Create and manage WhatsApp message templates"
    >
      <template #actions>
        <button
          class="l-btn l-btn--secondary"
          :disabled="isSyncing"
          @click="showSyncConfirm = true"
        >
          <FeatherIcon name="refresh-cw" class="w-4 h-4" :class="{ 'animate-spin': isSyncing }" />
          <span>{{ isSyncing ? 'Syncing Templates...' : 'Sync Templates' }}</span>
        </button>
        <button class="l-btn l-btn--primary" @click="$router.push({ name: 'WhatsAppTemplateEditor' })">
          <FeatherIcon name="plus" class="w-4 h-4" />
          <span>New Template</span>
        </button>
      </template>
    </PageHeader>

    <!-- Stats Cards -->
    <section class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
      <KpiCard
        label="Total"
        :value="store.templateMetrics.total"
        icon="layers"
        clickable
        :active="store.templateFilters.status === 'all'"
        @click="setStatusFilter('all')"
      />
      <KpiCard
        label="Approved"
        :value="store.templateMetrics.approved"
        icon="check-circle"
        clickable
        :active="store.templateFilters.status === 'APPROVED'"
        @click="setStatusFilter('APPROVED')"
      />
      <KpiCard
        label="In Review"
        :value="store.templateMetrics.pending"
        icon="clock"
        clickable
        :active="store.templateFilters.status === 'PENDING'"
        @click="setStatusFilter('PENDING')"
      />
      <KpiCard
        label="Rejected"
        :value="store.templateMetrics.rejected"
        icon="x-circle"
        clickable
        :active="store.templateFilters.status === 'REJECTED'"
        @click="setStatusFilter('REJECTED')"
      />
      <KpiCard
        label="Draft"
        :value="store.templateMetrics.draft"
        icon="edit-3"
        clickable
        :active="store.templateFilters.status === 'Draft'"
        @click="setStatusFilter('Draft')"
      />
    </section>

    <!-- Advanced filters bar -->
    <div class="filters-bar">
      <div class="filters-left">
        <div class="filter-select-wrapper">
          <label class="filter-lbl">Category</label>
          <select class="filter-select" v-model="store.templateFilters.category" @change="fetchTemplates">
            <option value="">All Categories</option>
            <option value="MARKETING">Marketing</option>
            <option value="UTILITY">Utility</option>
            <option value="AUTHENTICATION">Authentication</option>
            <option value="TRANSACTIONAL">Transactional</option>
            <option value="OTP">OTP</option>
          </select>
        </div>
        <div class="filter-select-wrapper">
          <label class="filter-lbl">Status</label>
          <select class="filter-select" v-model="store.templateFilters.status" @change="fetchTemplates">
            <option value="all">All Statuses</option>
            <option value="Draft">Draft</option>
            <option value="PENDING">In Review</option>
            <option value="APPROVED">Approved</option>
            <option value="REJECTED">Rejected</option>
            <option value="PAUSED">Paused</option>
            <option value="DISABLED">Disabled</option>
          </select>
        </div>

        <div class="filter-select-wrapper">
          <label class="filter-lbl">Date Updated</label>
          <select class="filter-select" v-model="store.templateFilters.dateRange" @change="onDateRangeChange">
            <option value="">Any Time</option>
            <option value="today">Today</option>
            <option value="7days">Last 7 Days</option>
            <option value="30days">Last 30 Days</option>
            <option value="custom">Custom Range</option>
          </select>
        </div>
      </div>
      <button v-if="hasActiveFilters" class="btn-clear-filters" @click="clearAllFilters">
        Clear Filters
      </button>
    </div>

    <!-- Custom Date Pickers -->
    <div v-if="store.templateFilters.dateRange === 'custom'" class="custom-dates-bar">
      <div class="custom-date-inputs">
        <input type="date" class="date-input" v-model="store.templateFilters.customDates.start" @change="fetchTemplates" />
        <span class="to-separator">to</span>
        <input type="date" class="date-input" v-model="store.templateFilters.customDates.end" @change="fetchTemplates" />
      </div>
    </div>

    <!-- Loading state -->
    <Shimmer v-if="store.templatesLoading" variant="cards" :count="6" />

    <!-- Empty state -->
    <div v-else-if="!store.templates.length" class="p-8">
      <EmptyState
        :title="store.templateSearch ? 'No templates match your search' : 'No templates found'"
        :description="store.templateSearch ? 'Try a different search term or clear filters.' : 'Create your first WhatsApp template to get started with messaging.'"
        variant="plain"
      >
        <template #actions>
          <button v-if="!store.templateSearch" class="l-btn l-btn--primary" @click="$router.push({ name: 'WhatsAppTemplateEditor' })">
            <FeatherIcon name="plus" class="w-4 h-4" />
            <span>Create Template</span>
          </button>
        </template>
      </EmptyState>
    </div>

    <!-- Table -->
    <div v-else class="l-table-scroll">
      <!-- Bulk action bar -->
      <div v-if="selectedNames.length" class="bulk-action-bar">
        <span>{{ selectedNames.length }} selected</span>
        <button class="btn-clear-filters" @click="selectedNames = []">Clear</button>
        <button class="btn-bulk-delete" @click="triggerBulkDelete">
          <FeatherIcon name="trash-2" class="w-3.5 h-3.5" />
          Delete Selected
        </button>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th class="checkbox-col l-th">
              <input type="checkbox" :checked="allSelected" @change="toggleSelectAll" />
            </th>
            <th class="sortable l-th" @click="setSort('template_name')">
              Template Name <FeatherIcon v-if="store.templateSort.field === 'template_name'" :name="store.templateSort.order === 'asc' ? 'arrow-up' : 'arrow-down'" class="w-3 h-3 sort-icon" />
            </th>
            <th class="sortable l-th" @click="setSort('category')">
              Category <FeatherIcon v-if="store.templateSort.field === 'category'" :name="store.templateSort.order === 'asc' ? 'arrow-up' : 'arrow-down'" class="w-3 h-3 sort-icon" />
            </th>
            <th class="sortable l-th" @click="setSort('language')">
              Language <FeatherIcon v-if="store.templateSort.field === 'language'" :name="store.templateSort.order === 'asc' ? 'arrow-up' : 'arrow-down'" class="w-3 h-3 sort-icon" />
            </th>
            <th class="sortable l-th" @click="setSort('status')">
              Status <FeatherIcon v-if="store.templateSort.field === 'status'" :name="store.templateSort.order === 'asc' ? 'arrow-up' : 'arrow-down'" class="w-3 h-3 sort-icon" />
            </th>
            <th class="l-th">Created By</th>
            <th class="sortable l-th" @click="setSort('modified')">
              Last Updated <FeatherIcon v-if="store.templateSort.field === 'modified'" :name="store.templateSort.order === 'asc' ? 'arrow-up' : 'arrow-down'" class="w-3 h-3 sort-icon" />
            </th>
            <th class="l-th actions-col"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="tpl in store.templates" :key="tpl.name" class="data-row">
            <td class="checkbox-col">
              <input type="checkbox" :value="tpl.name" v-model="selectedNames" />
            </td>
            <td class="cell-title font-medium cursor-pointer" @click="viewTemplateDetail(tpl)">
              <div class="cell-title-text hover:text-[var(--status-blue-fg)] transition-colors">{{ tpl.template_name || tpl.name }}</div>
              <div class="cell-sub-text">{{ tpl.name }}</div>
            </td>
            <td>
              <span class="category-tag">{{ tpl.category }}</span>
            </td>
            <td class="text-[var(--text-secondary)]">{{ tpl.language || '—' }}</td>
            <td>
              <StatusPill :status="tpl.status || 'Draft'" />
            </td>
            <td class="text-[var(--text-secondary)]">{{ tpl.owner || '—' }}</td>
            <td class="text-[var(--text-secondary)]">{{ formatDate(tpl.modified) }}</td>
            <td class="actions-col">
              <div class="row-actions">
                <button class="action-btn" @click="editTemplate(tpl.name)" title="Edit">
                  <FeatherIcon name="edit" class="w-3.5 h-3.5" />
                </button>
                <button class="action-btn" :disabled="duplicatingName === tpl.name" @click="duplicateTemplate(tpl)" title="Duplicate">
                  <FeatherIcon name="copy" class="w-3.5 h-3.5" />
                </button>
                <button class="action-btn text-[var(--status-red-fg)]" @click="triggerDelete(tpl)" title="Delete">
                  <FeatherIcon name="trash-2" class="w-3.5 h-3.5" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Pagination -->
      <div class="pagination-bar" v-if="totalPages > 1">
        <span>Showing {{ rangeStart }}–{{ rangeEnd }} of {{ store.templateTotal }}</span>
        <div class="pagination-controls">
          <button class="btn-clear-filters" :disabled="store.templatePage === 1" @click="goToPage(store.templatePage - 1)">Previous</button>
          <button class="btn-clear-filters" :disabled="store.templatePage === totalPages" @click="goToPage(store.templatePage + 1)">Next</button>
        </div>
      </div>
    </div>

    <!-- Bulk Delete Confirmation -->
    <ConfirmDialog
      :open="showBulkDeleteConfirm"
      title="Delete Selected Templates?"
      message="Choose where you want to delete these templates. This action cannot be undone."
      confirm="Delete Templates"
      cancel="Cancel"
      tone="danger"
      :busy="isBulkDeleting"
      busy-label="Deleting..."
      @confirm="confirmBulkDelete"
      @cancel="showBulkDeleteConfirm = false"
    >
      <div class="my-4 flex flex-col gap-2.5">
        <label class="flex items-start gap-3 p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-sunken)] cursor-pointer hover:bg-[var(--bg-sunken)] transition-colors select-none">
          <input type="radio" value="msuite" v-model="bulkDeleteTarget" :disabled="isBulkDeleting" class="mt-1 w-4 h-4 text-[var(--status-violet-fg)] focus:ring-[var(--brand)] border-[var(--border)]" />
          <div class="flex flex-col">
            <span class="text-sm font-semibold text-[var(--text-primary)]">Delete from MSuite only</span>
            <span class="text-xs text-[var(--text-secondary)]">Removes the template records locally from MSuite. They will remain active in Meta (WhatsApp).</span>
          </div>
        </label>
        
        <label
          class="flex items-start gap-3 p-3 rounded-lg border transition-colors select-none"
          :class="selectedTemplatesHaveMeta ? 'border-[var(--border)] bg-[var(--bg-sunken)] cursor-pointer hover:bg-[var(--bg-sunken)]' : 'border-[var(--border-soft)] bg-[var(--bg-sunken)] cursor-not-allowed opacity-60'"
        >
          <input type="radio" value="whatsapp" v-model="bulkDeleteTarget" :disabled="isBulkDeleting || !selectedTemplatesHaveMeta" class="mt-1 w-4 h-4 text-[var(--status-violet-fg)] focus:ring-[var(--brand)] border-[var(--border)]" />
          <div class="flex flex-col">
            <span class="text-sm font-semibold text-[var(--text-primary)]">Delete from WhatsApp and MSuite</span>
            <span class="text-xs text-[var(--text-secondary)]">Deletes the templates from Meta (WhatsApp) and removes them from MSuite database.</span>
          </div>
        </label>
      </div>
    </ConfirmDialog>

    <!-- Sync Confirmation -->
    <ConfirmDialog
      :open="showSyncConfirm"
      title="Sync WhatsApp Templates"
      message="Fetch the latest templates from connected WhatsApp Business Accounts and update MSuite."
      confirm="Sync Now"
      cancel="Cancel"
      tone="primary"
      :busy="isSyncing"
      busy-label="Syncing Templates..."
      @confirm="confirmSync"
      @cancel="showSyncConfirm = false"
    />

    <!-- Delete Confirmation -->
    <ConfirmDialog
      :open="showDeleteConfirm"
      title="Delete Template?"
      message="Choose where you want to delete this template. This action cannot be undone."
      confirm="Delete Template"
      cancel="Cancel"
      tone="danger"
      :busy="isDeleting"
      busy-label="Deleting..."
      @confirm="confirmDelete"
      @cancel="showDeleteConfirm = false"
    >
      <div class="my-4 flex flex-col gap-2.5">
        <label class="flex items-start gap-3 p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-sunken)] cursor-pointer hover:bg-[var(--bg-sunken)] transition-colors select-none">
          <input type="radio" value="msuite" v-model="deleteTargetType" :disabled="isDeleting" class="mt-1 w-4 h-4 text-[var(--status-violet-fg)] focus:ring-[var(--brand)] border-[var(--border)]" />
          <div class="flex flex-col">
            <span class="text-sm font-semibold text-[var(--text-primary)]">Delete from MSuite only</span>
            <span class="text-xs text-[var(--text-secondary)]">Removes this template record locally from MSuite. It will remain active in Meta (WhatsApp).</span>
          </div>
        </label>
        
        <label
          class="flex items-start gap-3 p-3 rounded-lg border transition-colors select-none"
          :class="deleteTargetStatus !== 'Draft' ? 'border-[var(--border)] bg-[var(--bg-sunken)] cursor-pointer hover:bg-[var(--bg-sunken)]' : 'border-[var(--border-soft)] bg-[var(--bg-sunken)] cursor-not-allowed opacity-60'"
        >
          <input type="radio" value="whatsapp" v-model="deleteTargetType" :disabled="isDeleting || deleteTargetStatus === 'Draft'" class="mt-1 w-4 h-4 text-[var(--status-violet-fg)] focus:ring-[var(--brand)] border-[var(--border)]" />
          <div class="flex flex-col">
            <span class="text-sm font-semibold text-[var(--text-primary)]">Delete from WhatsApp and MSuite</span>
            <span class="text-xs text-[var(--text-secondary)]">Deletes the template from Meta (WhatsApp) and removes it from MSuite database.</span>
          </div>
        </label>
      </div>
    </ConfirmDialog>

    <!-- Detail Drawer -->
    <Teleport to="body">
      <div v-if="activeTemplate || activeTemplateLoading" class="overlay" @click.self="activeTemplate = null; activeTemplateLoading = false">
        <aside class="drawer" role="dialog" aria-modal="true">
          <header class="head">
            <div>
              <h3>Template Details</h3>
              <p class="head-sub" v-if="activeTemplate">{{ activeTemplate.template_name }}</p>
            </div>
            <button class="close" @click="activeTemplate = null; activeTemplateLoading = false" aria-label="Close">×</button>
          </header>

          <Shimmer v-if="activeTemplateLoading" class="shm-pad" variant="rows" :count="5" />

          <div v-else-if="activeTemplate" class="drawer-body">
            <!-- Info Section: Metadata -->
            <section class="card">
              <div class="card-head">
                <span class="ic">
                  <FeatherIcon name="info" class="w-4 h-4 text-[var(--status-violet-fg)]" />
                </span>
                <div>
                  <div class="card-title">Metadata</div>
                  <div class="card-hint">Core configuration from Meta</div>
                </div>
              </div>
              
              <div class="info-grid">
                <div class="info-row">
                  <span class="info-label">Account</span>
                  <span class="info-value font-medium">{{ activeTemplate.whatsapp_account }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Category</span>
                  <span class="info-value">{{ activeTemplate.category }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Language</span>
                  <span class="info-value">{{ activeTemplate.language }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Variable Format</span>
                  <span class="info-value font-mono text-xs">{{ activeTemplate.parameter_format || 'POSITIONAL' }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Status</span>
                  <span class="info-value"><StatusPill :status="activeTemplate.status || 'Draft'" /></span>
                </div>
                <div class="info-row">
                  <span class="info-label">Last Updated</span>
                  <span class="info-value text-[var(--text-secondary)]">{{ formatDate(activeTemplate.modified) }}</span>
                </div>
              </div>
            </section>

            <!-- Optional Security Authentication Section -->
            <section v-if="activeTemplate.category === 'AUTHENTICATION'" class="card">
              <div class="card-head">
                <span class="ic">
                  <FeatherIcon name="shield" class="w-4 h-4 text-[var(--status-violet-fg)]" />
                </span>
                <div>
                  <div class="card-title">Authentication Options</div>
                </div>
              </div>
              <div class="info-grid">
                <div class="info-row">
                  <span class="info-label">Security Recommendation</span>
                  <span class="info-value">{{ activeTemplate.add_security_recommendation ? 'Yes' : 'No' }}</span>
                </div>
                <div class="info-row" v-if="activeTemplate.code_expiration_minutes">
                  <span class="info-label">Expiration</span>
                  <span class="info-value">{{ activeTemplate.code_expiration_minutes }} minutes</span>
                </div>
              </div>
            </section>

            <!-- WhatsApp Mockup Preview -->
            <section class="card mockup-card">
              <div class="card-head">
                <span class="ic">
                  <FeatherIcon name="message-circle" class="w-4 h-4 text-[var(--status-green-fg)]" />
                </span>
                <div>
                  <div class="card-title">WhatsApp Mockup</div>
                  <div class="card-hint">How the message appears to recipients</div>
                </div>
              </div>

              <div class="phone-frame-wrapper">
                <div class="phone-frame">
                  <div class="wa-preview-header">
                    <div class="wa-preview-avatar">
                      <FeatherIcon name="message-circle" class="w-4 h-4" />
                    </div>
                    <div class="wa-preview-header-info">
                      <span class="wa-preview-sender">{{ activeTemplate.whatsapp_account }}</span>
                      <span class="wa-preview-status">Template preview</span>
                    </div>
                  </div>

                  <div class="wa-chat-bg">
                    <div class="wa-message-card">
                      <div class="wa-message-content">
                        <!-- Header -->
                        <div v-if="activeTemplate.header_type === 'TEXT' && activeTemplate.header" class="wa-msg-header" v-html="formattedHeader"></div>
                        <div v-else-if="activeTemplate.header_type === 'IMAGE'" class="wa-msg-media">
                          <img v-if="activeTemplate.media_sample" :src="activeTemplate.media_sample" class="img-preview" alt="Preview" />
                          <div v-else class="media-placeholder">
                            <FeatherIcon name="image" class="w-10 h-10 text-[var(--text-tertiary)]" />
                            <span class="media-placeholder-text">Image</span>
                          </div>
                        </div>
                        <div v-else-if="activeTemplate.header_type === 'VIDEO'" class="wa-msg-media">
                          <video v-if="activeTemplate.media_sample" :src="activeTemplate.media_sample" class="img-preview" controls></video>
                          <div v-else class="media-placeholder">
                            <FeatherIcon name="video" class="w-10 h-10 text-[var(--text-tertiary)]" />
                            <span class="media-placeholder-text">Video</span>
                          </div>
                        </div>
                        <div v-else-if="activeTemplate.header_type === 'DOCUMENT'" class="wa-msg-media wa-msg-doc">
                          <FeatherIcon name="file-text" class="w-6 h-6 text-[var(--ink-600)] shrink-0" />
                          <span class="media-placeholder-text font-medium text-[var(--ink-800)] text-xs break-all leading-snug">
                            {{ activeTemplate.media_sample ? getMediaFilename(activeTemplate.media_sample) : 'Document.pdf' }}
                          </span>
                        </div>
                        <div v-else-if="activeTemplate.header_type === 'LOCATION'" class="wa-msg-media">
                          <FeatherIcon name="map-pin" class="w-10 h-10 text-[var(--text-tertiary)]" />
                          <span class="media-placeholder-text">Location (set at send time)</span>
                        </div>

                        <!-- Catalog template: thumbnail header + WhatsApp's fixed header/sub-header -->
                        <template v-if="activeTemplate.template_type === 'CATALOGUE'">
                          <div class="wa-msg-media">
                            <FeatherIcon name="shopping-bag" class="w-10 h-10 text-[var(--text-tertiary)]" />
                            <span class="media-placeholder-text">Catalog thumbnail</span>
                          </div>
                          <div class="wa-msg-catalog-title">View {{ activeTemplate.whatsapp_account }}'s Catalog on WhatsApp</div>
                          <div class="wa-msg-catalog-sub">Browse pictures and details of their offerings.</div>
                        </template>

                        <!-- Body -->
                        <div class="wa-msg-body" v-html="formattedBody"></div>

                        <!-- Footer -->
                        <div v-if="activeTemplate.footer" class="wa-msg-footer">{{ activeTemplate.footer }}</div>

                        <div class="wa-msg-time">{{ mockTime }}</div>
                      </div>

                      <!-- Catalog template's fixed "View catalog" button -->
                      <div v-if="activeTemplate.template_type === 'CATALOGUE'" class="wa-card-buttons">
                        <div class="wa-card-button-row">
                          <FeatherIcon name="shopping-bag" class="w-4 h-4 wa-btn-icon" />
                          <span class="wa-btn-text">View catalog</span>
                        </div>
                      </div>

                      <!-- Buttons (hidden for carousel — its buttons live on each card) -->
                      <div v-if="!activeTemplate.is_carousel && activeTemplate.richButtons && activeTemplate.richButtons.length" class="wa-card-buttons">
                        <div v-for="btn in activeTemplate.richButtons" :key="btn.local_id" class="wa-card-button-row">
                          <FeatherIcon v-if="btn.type === 'URL'" name="external-link" class="w-4 h-4 wa-btn-icon" />
                          <FeatherIcon v-else-if="btn.type === 'PHONE_NUMBER' || btn.type === 'VOICE_CALL'" name="phone" class="w-4 h-4 wa-btn-icon" />
                          <FeatherIcon v-else-if="btn.type === 'FLOW'" name="shuffle" class="w-4 h-4 wa-btn-icon" />
                          <FeatherIcon v-else-if="btn.type === 'COPY_CODE'" name="copy" class="w-4 h-4 wa-btn-icon" />
                          <FeatherIcon v-else name="corner-up-right" class="w-4 h-4 wa-btn-icon" />
                          <span class="wa-btn-text">{{ btn.text || 'Button' }}</span>
                        </div>
                      </div>

                      <!-- Product Card Carousel — body text (above) + scrollable product cards -->
                      <div v-if="activeTemplate.is_carousel && activeTemplate.carousel_cards && activeTemplate.carousel_cards.length" class="wa-carousel-row">
                        <div v-for="(card, idx) in activeTemplate.carousel_cards" :key="idx" class="wa-carousel-card">
                          <div class="wa-carousel-img">
                            <FeatherIcon name="image" class="w-8 h-8 text-[var(--text-tertiary)]" />
                          </div>
                          <div class="wa-carousel-body">
                            <span class="wa-carousel-title">Product name</span>
                            <span class="wa-carousel-price">$0.00</span>
                          </div>
                          <div class="wa-carousel-btn">
                            <FeatherIcon v-if="card.button_type === 'URL'" name="external-link" class="w-3.5 h-3.5 wa-btn-icon" />
                            <FeatherIcon v-else name="shopping-bag" class="w-3.5 h-3.5 wa-btn-icon" />
                            <span>{{ card.button_label || 'View' }}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>

          <footer class="foot" v-if="activeTemplate">
            <button class="btn btn-default" @click="activeTemplate = null">Close</button>
            <div class="grow"></div>
            <button class="btn btn-primary" @click="editTemplate(activeTemplate.name)">Edit Template</button>
          </footer>
        </aside>
      </div>
    </Teleport>
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

const store = useWhatsApp()
const router = useRouter()

const showDeleteConfirm = ref(false)
const deleteTargetName = ref('')
const deleteTargetStatus = ref('')
const deleteTargetType = ref('whatsapp')
const isDeleting = ref(false)

const showSyncConfirm = ref(false)
const isSyncing = ref(false)

const selectedNames = ref([])
const showBulkDeleteConfirm = ref(false)
const bulkDeleteTarget = ref('whatsapp')
const isBulkDeleting = ref(false)
const duplicatingName = ref('')

const selectedTemplatesHaveMeta = computed(() => {
  return selectedNames.value.some(name => {
    const tpl = store.templates.find(t => t.name === name)
    return tpl && tpl.status !== 'Draft'
  })
})

const activeTemplate = ref(null)
const activeTemplateLoading = ref(false)

const mockTime = computed(() => {
  const now = new Date()
  return now.toLocaleTimeString(void 0, { hour: '2-digit', minute: '2-digit' })
})

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

const formattedBody = computed(() => {
  if (!activeTemplate.value) return ''
  const safeBody = escapeHtml(activeTemplate.value.template || '')
  return safeBody.replace(/\{\{([^}]+)\}\}/g, '<strong class="text-[var(--status-orange-fg)] font-semibold">{{$1}}</strong>')
})

const formattedHeader = computed(() => {
  if (!activeTemplate.value) return ''
  const safeHeader = escapeHtml(activeTemplate.value.header || '')
  return safeHeader.replace(/\{\{([^}]+)\}\}/g, '<strong class="text-[var(--status-orange-fg)] font-semibold">{{$1}}</strong>')
})

function getMediaFilename(url) {
  if (!url) return 'Document.pdf'
  const cleanUrl = String(url).split('?')[0].split('#')[0]
  const filename = cleanUrl.split('/').pop()
  return filename ? decodeURIComponent(filename) : 'Document.pdf'
}

async function viewTemplateDetail(tpl) {
  activeTemplate.value = null
  activeTemplateLoading.value = true
  try {
    const detail = await store.fetchTemplateDetail(tpl.name)
    let buttons = []
    let useLinkTracking = true
    if (detail.button_configuration) {
      try {
        const parsed = JSON.parse(detail.button_configuration)
        if (Array.isArray(parsed)) {
          buttons = parsed
        } else if (parsed && parsed.buttons) {
          buttons = parsed.buttons
          useLinkTracking = parsed.use_link_tracking !== undefined ? parsed.use_link_tracking : true
        }
      } catch (e) {
        console.error('Failed to parse button_configuration', e)
      }
    }
    
    let rawBtns = []
    if (detail.buttons && detail.buttons.length) {
      rawBtns = detail.buttons
    } else if (buttons && buttons.length) {
      rawBtns = buttons
    }
    
    detail.richButtons = rawBtns.map((b, i) => {
      let type = 'QUICK_REPLY'
      const rawType = (b.button_type || b.type || '').trim().toUpperCase()
      if (rawType === 'VISIT WEBSITE' || rawType === 'URL') type = 'URL'
      else if (rawType === 'CALL PHONE' || rawType === 'PHONE_NUMBER' || rawType === 'PHONE') type = 'PHONE_NUMBER'
      else if (rawType === 'VOICE CALL' || rawType === 'VOICE_CALL') type = 'VOICE_CALL'
      else if (rawType === 'FLOW') type = 'FLOW'
      else if (rawType === 'OTP' || rawType === 'COPY_CODE' || rawType === 'COPY CODE') type = 'COPY_CODE'

      const extra = (buttons && buttons[i] && (buttons[i].type === type || buttons[i].button_type === type)) ? buttons[i] : {}
      return {
        type,
        text: b.button_label || b.text || 'Button',
        url: b.website_url || b.url || '',
        url_type: b.url_type || extra.url_type || 'Static',
        example_url: b.example_url || extra.example_url || '',
        phone: b.phone_number || b.phone || '',
        voice_call_phone: b.voice_call_phone || '',
        active_for: extra.active_for || '7 days',
        country: extra.country || detail.country || '',
        flow_name: extra.flow_name || b.flow || '',
        flow_id: b.flow_id || b.flow || extra.flow_id || '',
        coupon_code: detail.offer_code || extra.coupon_code || '',
      }
    })
    activeTemplate.value = detail
  } catch (e) {
    console.error('Failed to fetch template detail', e)
  } finally {
    activeTemplateLoading.value = false
  }
}

const allSelected = computed(() =>
  store.templates.length > 0 && selectedNames.value.length === store.templates.length
)

const totalPages = computed(() =>
  Math.max(1, Math.ceil(store.templateTotal / store.templatePageSize))
)
const rangeStart = computed(() => (store.templatePage - 1) * store.templatePageSize + 1)
const rangeEnd = computed(() => Math.min(store.templatePage * store.templatePageSize, store.templateTotal))

const statusFilters = [
  { value: 'all', label: 'All' },
  { value: 'Draft', label: 'Draft', dot: 'var(--ink-300)' },
  { value: 'PENDING', label: 'In Review', dot: '#eab308' },
  { value: 'APPROVED', label: 'Approved', dot: '#22c55e' },
  { value: 'REJECTED', label: 'Rejected', dot: '#ef4444' },
  { value: 'PAUSED', label: 'Paused', dot: '#f59e0b' },
  { value: 'DISABLED', label: 'Disabled', dot: 'var(--ink-500)' },
]

const hasActiveFilters = computed(() => {
  const f = store.templateFilters
  return f.status !== 'all' || f.category !== '' || f.language !== '' || f.dateRange !== '' || store.templateSearch !== ''
})

async function fetchTemplates() {
  store.templatePage = 1
  selectedNames.value = []
  await store.fetchTemplates()
}

async function goToPage(page) {
  store.templatePage = page
  selectedNames.value = []
  await store.fetchTemplates()
}

async function setSort(field) {
  if (store.templateSort.field === field) {
    store.templateSort.order = store.templateSort.order === 'asc' ? 'desc' : 'asc'
  } else {
    store.templateSort.field = field
    store.templateSort.order = 'asc'
  }
  await goToPage(1)
}

function toggleSelectAll(e) {
  selectedNames.value = e.target.checked ? store.templates.map(t => t.name) : []
}

async function setStatusFilter(status) {
  store.templateFilters.status = status
  await fetchTemplates()
}

function onDateRangeChange() {
  if (store.templateFilters.dateRange !== 'custom') {
    store.templateFilters.customDates.start = ''
    store.templateFilters.customDates.end = ''
  }
  fetchTemplates()
}

function clearAllFilters() {
  store.templateFilters.status = 'all'
  store.templateFilters.category = ''
  store.templateFilters.language = ''
  store.templateFilters.dateRange = ''
  store.templateFilters.customDates.start = ''
  store.templateFilters.customDates.end = ''
  store.templateSearch = ''
  fetchTemplates()
}

function editTemplate(name) {
  router.push({ name: 'WhatsAppTemplateEditor', query: { name } })
}

async function duplicateTemplate(tpl) {
  duplicatingName.value = tpl.name
  try {
    const res = await store.duplicateTemplate(tpl.name)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'Template duplicated.', indicator: 'green' })
    }
    router.push({ name: 'WhatsAppTemplateEditor', query: { name: res.name } })
  } catch (e) {
    console.error('Failed to duplicate template', e)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: e.message || 'Failed to duplicate template.', indicator: 'red' })
    }
  } finally {
    duplicatingName.value = ''
  }
}

function triggerDelete(tpl) {
  deleteTargetName.value = tpl.name
  deleteTargetStatus.value = tpl.status
  if (tpl.status === 'Draft') {
    deleteTargetType.value = 'msuite'
  } else {
    deleteTargetType.value = 'whatsapp'
  }
  showDeleteConfirm.value = true
}

function triggerBulkDelete() {
  if (selectedTemplatesHaveMeta.value) {
    bulkDeleteTarget.value = 'whatsapp'
  } else {
    bulkDeleteTarget.value = 'msuite'
  }
  showBulkDeleteConfirm.value = true
}

async function confirmBulkDelete() {
  isBulkDeleting.value = true
  try {
    const deleteFromWhatsapp = bulkDeleteTarget.value === 'whatsapp'
    const res = await store.bulkDeleteTemplates(selectedNames.value, deleteFromWhatsapp)
    showBulkDeleteConfirm.value = false
    selectedNames.value = []
    if (window.frappe?.show_alert) {
      const failedNote = res?.failed?.length ? ` (${res.failed.length} failed)` : ''
      window.frappe.show_alert({
        message: `Deleted ${res?.deleted?.length || 0} template(s)${failedNote}.`,
        indicator: res?.failed?.length ? 'orange' : 'green'
      })
    }
  } catch (e) {
    console.error('Failed to bulk delete templates', e)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: e.message || 'Failed to delete templates.', indicator: 'red' })
    }
  } finally {
    isBulkDeleting.value = false
  }
}

async function confirmDelete() {
  isDeleting.value = true
  try {
    const deleteFromWhatsapp = deleteTargetType.value === 'whatsapp'
    await store.deleteTemplate(deleteTargetName.value, deleteFromWhatsapp)
    showDeleteConfirm.value = false
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'Template deleted.', indicator: 'green' })
    }
  } catch (e) {
    console.error('Failed to delete template', e)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'Failed to delete template.', indicator: 'red' })
    }
  } finally {
    isDeleting.value = false
  }
}

async function confirmSync() {
  isSyncing.value = true
  try {
    const res = await store.syncTemplates()
    showSyncConfirm.value = false
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({
        message: res || 'Successfully synced templates from Meta.',
        indicator: 'green'
      })
    }
  } catch (e) {
    console.error('Failed to sync templates', e)
    let errMsg = e.message || e.toString() || 'Failed to sync templates.'
    if (errMsg.includes('No active WhatsApp Account found')) {
      errMsg = 'No WhatsApp Business Account connected.'
    }
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({
        message: errMsg,
        indicator: 'red'
      })
    }
  } finally {
    isSyncing.value = false
  }
}

function formatDate(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

onMounted(async () => {
  await Promise.all([store.fetchTemplateMetrics(), store.fetchTemplates()])
})
</script>

<style scoped>
.wa-page {
  width: 100%;
  padding: 0;
  font-family: var(--font-stack, system-ui, -apple-system, sans-serif);
  color: var(--ink-900);
}

/* ── Header (matches Campaigns/Ads) ──────────────────────── */
.wa-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
.wa-title { margin: 0; font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }
.wa-subtitle { margin: 4px 0 0; font-size: 14px; color: var(--text-secondary); }
.wa-actions { display: flex; align-items: center; gap: 12px; }

.wa-search { position: relative; display: flex; align-items: center; }
.search-icon { position: absolute; left: 10px; width: 16px; height: 16px; color: var(--text-tertiary); pointer-events: none; }
.search-input { height: 38px; width: 220px; padding: 0 12px 0 34px; border: 1.5px solid var(--border-base); border-radius: 10px; font-size: 13px; color: var(--text-primary); background: var(--surface-surface); outline: none; transition: border-color 0.15s; }
.search-input::placeholder { color: var(--text-tertiary); }
.search-input:focus { border-color: var(--brand-color); }

.btn-create { display: inline-flex; align-items: center; gap: 6px; height: 38px; padding: 0 18px; border: none; border-radius: 10px; background: var(--brand); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; transition: transform 0.08s, box-shadow 0.15s; box-shadow: var(--shadow-sm); }
.btn-create:hover { box-shadow: var(--shadow-md); }
.btn-create:active { transform: translateY(1px); }

/* ── Advanced Filters ─────────────────────────────────── */
.filters-bar { display: flex; align-items: flex-end; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.filters-left { display: flex; gap: 12px; flex-wrap: wrap; }
.filter-select-wrapper { display: flex; flex-direction: column; gap: 4px; }
.filter-lbl { font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em; }
.filter-select { height: 36px; padding: 0 10px; border: 1.5px solid var(--border-base); border-radius: 8px; font-size: 13px; color: var(--text-primary); background: var(--surface-surface); outline: none; min-width: 140px; }
.filter-select:focus { border-color: var(--brand-color); }
.btn-clear-filters { height: 36px; padding: 0 14px; border: 1.5px solid var(--border-base); border-radius: 8px; background: var(--surface-surface); font-size: 12px; font-weight: 500; color: var(--text-secondary); cursor: pointer; }
.btn-clear-filters:hover { border-color: var(--ink-200); color: var(--text-primary); }
.btn-clear-filters:disabled { opacity: 0.5; cursor: not-allowed; }

.custom-dates-bar { margin-bottom: 16px; }
.custom-date-inputs { display: flex; align-items: center; gap: 8px; }
.date-input { height: 36px; padding: 0 10px; border: 1.5px solid var(--border-base); border-radius: 8px; font-size: 13px; color: var(--text-primary); background: var(--surface-surface); }
.to-separator { font-size: 13px; color: var(--text-tertiary); }

/* ── Loading / Empty ──────────────────────────────────── */
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
.sortable { cursor: pointer; user-select: none; }
.sortable:hover { color: var(--brand-color); }
.sort-icon { display: inline-block; vertical-align: middle; margin-left: 2px; }
.pagination-bar { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-top: 1px solid var(--border-base); background: var(--surface-page); font-size: 12px; color: var(--text-secondary); }
.pagination-controls { display: flex; gap: 8px; }

/* ── Table ────────────────────────────────────────────── */
.table-wrapper { background: var(--surface-surface); border: 1px solid var(--border-base); border-radius: 14px; overflow-x: auto;
  overflow-y: hidden; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { padding: 12px 16px; text-align: left; font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid var(--border-base); background: var(--surface-page); }
.data-table td { padding: 14px 16px; border-bottom: 1px solid var(--border-soft); vertical-align: middle; }
.data-row:last-child td { border-bottom: none; }
.data-row:hover { background: var(--surface-page); }
.cell-title { cursor: pointer; }
.cell-title:hover .cell-title-text { color: var(--brand-color); }
.cell-title-text { font-weight: 500; color: var(--text-primary); transition: color 0.15s; }
.cell-sub-text { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; font-family: monospace; }
.category-tag { font-size: 11px; font-weight: 500; padding: 3px 8px; border-radius: 6px; background: var(--brand-lighter); color: var(--brand-500); }
.actions-col { width: 100px; text-align: right; }
.row-actions { display: flex; align-items: center; gap: 4px; justify-content: flex-end; }
.action-btn { width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border: none; background: transparent; border-radius: 6px; color: var(--text-secondary); cursor: pointer; transition: background 0.1s, color 0.1s; }
.action-btn:hover { background: var(--border-soft); color: var(--text-primary); }
.text-rose-600 { color: var(--status-red-fg); }
.action-btn.text-rose-600:hover { background: var(--status-red-bg); color: var(--status-red-fg); }

.btn-sync {
  height: 38px !important;
  border-radius: 10px !important;
  border-width: 1.5px !important;
  font-size: 13px !important;
  font-weight: 600 !important;
  color: var(--ink-500) !important;
}


/* Utility color classes */
.text-slate-800 { color: var(--ink-800); } .text-slate-600 { color: var(--ink-600); } .text-slate-500 { color: var(--ink-500); }
.text-emerald-600 { color: var(--status-green-fg); } .text-amber-600 { color: var(--status-amber-fg); } .text-rose-600 { color: var(--status-red-fg); }
.text-brand-500 { color: var(--brand); } .text-emerald-500 { color: var(--emerald-500); } .text-amber-500 { color: var(--orange-500); }
.text-rose-500 { color: var(--rose-500); } .text-slate-400 { color: var(--ink-300); }
.bg-emerald-50 { background-color: var(--status-green-bg); } .bg-amber-50 { background-color: var(--status-amber-bg); }
.bg-rose-50 { background-color: var(--status-red-bg); } .bg-slate-50 { background-color: var(--ink-25); }
.font-medium { font-weight: 500; }

.overlay {
  position: fixed; inset: 0;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(2px);
  z-index: 100;
  display: flex; justify-content: flex-end;
}

.drawer {
  width: 100%; max-width: 540px;
  height: 100%;
  background: var(--ink-25);
  display: flex; flex-direction: column;
  box-shadow: -10px 0 40px rgba(0, 0, 0, 0.18);
  animation: slide-in .25s cubic-bezier(0.22, 0.61, 0.36, 1);
}
@keyframes slide-in {
  from { transform: translateX(40px); opacity: 0.4; }
  to   { transform: translateX(0);    opacity: 1; }
}

.head {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 22px 28px;
  background: var(--surface-surface);
  border-bottom: 1px solid var(--ink-100);
  gap: 16px;
}
.head h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ink-900);
}
.head-sub {
  margin: 4px 0 0;
  color: var(--ink-500);
  font-size: 13px;
  line-height: 1.5;
}
.close {
  background: transparent; border: none;
  font-size: 24px; line-height: 1; padding: 0 6px;
  color: var(--ink-500); cursor: pointer;
  flex-shrink: 0;
}
.close:hover { color: var(--ink-900); }

.drawer-loading {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-secondary);
}
.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--ink-100);
  border-top-color: var(--brand-color, var(--brand));
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.drawer-body {
  flex: 1;
  min-width: 0;
  padding: 20px 24px 32px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.phone-frame-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 14px;
}

.info-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 14px;
}
.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--ink-50);
  font-size: 13px;
}
.info-row:last-child {
  border-bottom: none;
}
.info-label {
  color: var(--text-secondary, var(--ink-500));
  font-weight: 500;
}
.info-value {
  color: var(--text-primary, var(--ink-900));
}

.card {
  background: var(--surface-surface);
  border: 1px solid var(--border-base, var(--ink-100));
  border-radius: var(--radius-lg, 12px);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.card-head {
  display: flex;
  gap: 12px;
  align-items: center;
}
.ic {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--ink-50);
}
.card-title {
  font-weight: 700;
  font-size: 15px;
  color: var(--ink-900);
}
.card-hint {
  color: var(--ink-500);
  font-size: 12px;
  margin-top: 2px;
  line-height: 1.4;
}

.foot {
  display: flex; gap: 12px;
  align-items: center;
  padding: 16px 24px;
  background: var(--surface-surface);
  border-top: 1px solid var(--ink-100);
}
.grow { flex: 1; }
.btn {
  height: 42px; padding: 0 22px;
  border-radius: 10px;
  font-weight: 500; font-size: 14px;
  cursor: pointer;
  border: 1.5px solid transparent;
  transition: background .12s, border-color .12s, transform .05s;
}
.btn:active { transform: translateY(1px); }
.btn-default {
  background: var(--surface-surface);
  border-color: var(--ink-100);
  color: var(--ink-700, var(--ink-600));
}
.btn-default:hover {
  border-color: var(--brand-500, #3b82f6);
  color: var(--ink-900);
}
.btn-primary {
  background: var(--brand-color, var(--brand));
  color: var(--text-on-brand);
  border-color: var(--brand-color, var(--brand));
}
.btn-primary:hover {
  background: var(--status-blue-fg);
  border-color: var(--status-blue-fg);
}

/* ── WhatsApp Phone Mockup ────────────────────────────── */
.phone-frame-wrapper {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}
.phone-frame {
  width: 100%;
  max-width: 340px;
  border-radius: 32px;
  border: 10px solid #1e293b;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  background: #efeae2;
}
.wa-preview-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: #075e54;
}
.wa-preview-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.wa-preview-header-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.wa-preview-sender {
  color: #fff;
  font-size: 12.5px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.wa-preview-status {
  color: rgba(255, 255, 255, 0.7);
  font-size: var(--fs-2xs);
}
.wa-chat-bg {
  background: #efeae2;
  background-image: radial-gradient(#d1d7db 1px, transparent 1px);
  background-size: 16px 16px;
  min-height: 360px;
  max-height: 580px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 14px 10px 24px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 6px;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.3) transparent;
}
.wa-chat-bg::-webkit-scrollbar {
  width: 6px;
}
.wa-chat-bg::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
}
.wa-chat-bg::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.3);
  border-radius: 4px;
}
.wa-chat-bg::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.5);
}
.wa-message-card {
  background: var(--bg-surface);
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.12);
  overflow: hidden;
  width: 100%;
  max-width: 100%;
  align-self: flex-start;
}
.wa-message-content {
  padding: 10px 12px 6px;
}
.wa-msg-header {
  font-weight: 700;
  font-size: 13px;
  color: #111b21;
  margin-bottom: 6px;
}
.wa-msg-media {
  border-radius: 8px;
  overflow: hidden;
  background: var(--ink-50);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 140px;
}
.wa-msg-media.wa-msg-doc {
  min-height: 60px;
  justify-content: flex-start;
  padding: 12px;
  gap: 10px;
  background: var(--ink-50);
}
.img-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.media-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.media-placeholder-text {
  font-size: 12px;
  color: var(--text-secondary);
}
.wa-msg-body {
  font-size: 13.5px;
  color: #111b21;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.wa-msg-footer {
  font-size: 11px;
  color: #667781;
  margin-top: 4px;
}
.wa-msg-catalog-title {
  font-weight: 700;
  font-size: 13.5px;
  color: #111b21;
  line-height: 1.35;
}
.wa-msg-catalog-sub {
  font-size: 12px;
  color: #667781;
  margin-bottom: 6px;
  line-height: 1.35;
}
.wa-msg-time {
  font-size: var(--fs-2xs);
  color: #667781;
  text-align: right;
  margin-top: 2px;
}
.wa-card-buttons {
  border-top: 1px solid var(--ink-50);
  display: flex;
  flex-direction: column;
}
.wa-card-button-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 38px;
  border-bottom: 1px solid var(--ink-50);
  color: #008069;
  font-size: 13px;
  font-weight: 500;
  cursor: default;
}
.wa-card-button-row:last-child {
  border-bottom: none;
}
.wa-btn-icon {
  color: #008069;
}
.wa-btn-text {
  max-width: 80%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Product Card Carousel */
.wa-carousel-row {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  margin-top: 6px;
  padding: 6px 2px 2px;
}
.wa-carousel-card {
  flex: 0 0 130px;
  background: var(--bg-surface);
  border: 1px solid var(--ink-100);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.wa-carousel-img {
  height: 90px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ink-50);
}
.wa-carousel-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
}
.wa-carousel-title {
  font-size: 12px;
  font-weight: 500;
  color: #111b21;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.wa-carousel-price {
  font-size: 11px;
  color: #667781;
}
.wa-carousel-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 8px 6px;
  font-size: 12px;
  font-weight: 500;
  color: #008069;
  border-top: 1px solid var(--ink-50);
}
</style>
