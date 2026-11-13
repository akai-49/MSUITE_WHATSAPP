<!--
  WhatsAppBulkMessages — list page for Bulk WhatsApp Messages (Campaigns/Broadcasts).

  Matches the Campaigns/AdsManager pattern: header, stats, filter pills,
  advanced filters, search, table with row actions, empty state.
-->
<template>
  <div class="wa-page">
    <!-- Header -->
    <PageHeader
      title="Bulk Messages"
      subtitle="Send and schedule bulk WhatsApp campaigns"
    >
      <template #actions>
        <button class="l-btn l-btn--primary" data-tour="new-whatsapp-broadcast" @click="startNewBroadcast">
          <FeatherIcon name="plus" class="w-4 h-4" />
          <span>New Broadcast</span>
        </button>
      </template>
    </PageHeader>

    <!-- Stats Cards -->
    <section class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
      <KpiCard
        label="Total"
        :value="store.bulkMetrics.total"
        icon="layers"
        clickable
        :active="store.bulkFilters.status === 'all'"
        @click="setStatusFilter('all')"
      />
      <KpiCard
        label="In Progress"
        :value="store.bulkMetrics.inProgress"
        icon="clock"
        clickable
        :active="store.bulkFilters.status === 'In Progress'"
        @click="setStatusFilter('In Progress')"
      />
      <KpiCard
        label="Scheduled"
        :value="store.bulkMetrics.scheduled"
        icon="calendar"
        clickable
        :active="store.bulkFilters.status === 'Scheduled'"
        @click="setStatusFilter('Scheduled')"
      />
      <KpiCard
        label="Completed"
        :value="store.bulkMetrics.completed"
        icon="check-circle"
        clickable
        :active="store.bulkFilters.status === 'Completed'"
        @click="setStatusFilter('Completed')"
      />
      <KpiCard
        label="Failed"
        :value="store.bulkMetrics.partiallyFailed"
        icon="alert-triangle"
        clickable
        :active="store.bulkFilters.status === 'Partially Failed'"
        @click="setStatusFilter('Partially Failed')"
      />
    </section>



    <!-- Loading state -->
    <div class="loading-state" v-if="store.bulkMessagesLoading">
      <div v-for="n in 4" :key="n" class="skeleton-row">
        <div class="skeleton skeleton-title"></div>
        <div class="skeleton skeleton-pill"></div>
        <div class="skeleton skeleton-text"></div>
        <div class="skeleton skeleton-text-sm"></div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!store.bulkMessages.length" class="p-8">
      <EmptyState
        :title="store.bulkSearch ? 'No broadcasts match your search' : 'No broadcasts found'"
        :description="store.bulkSearch ? 'Try a different search term or clear filters.' : 'Send your first bulk WhatsApp campaign to reach your customers.'"
        variant="plain"
      >
        <template #actions>
          <button v-if="!store.bulkSearch" class="l-btn l-btn--primary" @click="startNewBroadcast">
            <FeatherIcon name="plus" class="w-4 h-4" />
            <span>Create Broadcast</span>
          </button>
        </template>
      </EmptyState>
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
            <th class="l-th">Broadcast Name</th>
            <th class="l-th">Template</th>
            <th class="l-th">Audience</th>
            <th class="l-th">Progress / Status</th>
            <th class="l-th">Scheduled Time</th>
            <th class="l-th">Created At</th>
            <th class="l-th">Last Synced</th>
            <th class="l-th actions-col"></th>
          </tr>
        </thead>
        <tbody>
          <tr class="data-row" v-for="msg in store.bulkMessages" :key="msg.name" :class="{ 'bg-[var(--bg-sunken)]': selectedNames.includes(msg.name) }">
            <td class="checkbox-col" @click.stop>
              <input
                type="checkbox"
                class="rounded border-[var(--ink-200)] dark:border-slate-700 text-[var(--brand)] focus:ring-[var(--brand)]"
                :checked="selectedNames.includes(msg.name)"
                @change="toggleSelect(msg.name)"
              />
            </td>
            <td class="cell-title font-medium" @click="viewBroadcast(msg.name)">
              <div class="cell-title-text">{{ msg.title || msg.name }}</div>
              <div class="cell-sub-text">{{ msg.name }}</div>
            </td>
            <td>
              <span class="template-tag" v-if="msg.template">
                <FeatherIcon name="file-text" class="w-3 h-3 text-[var(--status-violet-fg)]" />
                {{ msg.template }}
              </span>
              <span class="text-[var(--text-tertiary)]" v-else>—</span>
            </td>
            <td>
              <div class="audience-info" v-if="msg.recipient_list || msg.recipient_type">
                <span class="font-medium text-[var(--text-primary)]">{{ msg.recipient_count || 0 }} recipients</span>
                <span class="cell-sub-text" v-if="msg.recipient_list">{{ msg.recipient_list }}</span>
                <span class="cell-sub-text" v-else>{{ msg.recipient_type }}</span>
              </div>
              <span class="text-[var(--text-tertiary)]" v-else>—</span>
            </td>
            <td>
              <div class="status-cell">
                <StatusPill :status="msg.status || 'Draft'" />
                <div class="progress-bar-container" v-if="msg.status === 'In Progress' || msg.status === 'Queued' || msg.status === 'Completed' || msg.status === 'Partially Failed'">
                  <div class="progress-bar-bg">
                    <div class="progress-bar-fill progress-bar-success" :style="{ width: getSuccessPercent(msg) + '%' }"></div>
                    <div class="progress-bar-fill progress-bar-danger" :style="{ width: getFailedPercent(msg) + '%' }"></div>
                  </div>
                  <div class="progress-text">
                    <span class="text-[var(--status-green-fg)] font-semibold">{{ msg.sent_count || 0 }} sent</span>
                    <span v-if="msg.failed_count" class="text-[var(--status-red-fg)] font-semibold ml-1.5">{{ msg.failed_count }} failed</span>
                    <span class="text-[var(--text-tertiary)]"> / {{ msg.recipient_count || 0 }} total</span>
                  </div>
                </div>
              </div>
            </td>
            <td class="text-[var(--text-secondary)]">
              {{ msg.scheduled_time ? formatDate(msg.scheduled_time, true) : 'Immediate' }}
            </td>
            <td class="text-[var(--text-secondary)]">{{ formatDate(msg.creation, true) }}</td>
            <td class="text-[var(--text-secondary)]">{{ formatDate(msg.modified, true) }}</td>
            <td class="actions-col">
              <div class="row-actions">
                <button v-if="canRetry(msg)" class="action-btn text-[var(--status-amber-fg)]" @click="retryBroadcast(msg)" :disabled="busyName === msg.name" title="Retry Failed">
                  <FeatherIcon name="refresh-cw" class="w-3.5 h-3.5" />
                </button>
                <button v-if="canPause(msg)" class="action-btn" @click="pauseBroadcast(msg)" :disabled="busyName === msg.name" title="Pause Broadcast">
                  <FeatherIcon name="pause" class="w-3.5 h-3.5" />
                </button>
                <button v-if="canResume(msg)" class="action-btn text-[var(--status-green-fg)]" @click="resumeBroadcast(msg)" :disabled="busyName === msg.name" title="Resume Broadcast">
                  <FeatherIcon name="play" class="w-3.5 h-3.5" />
                </button>
                <button v-if="canCancel(msg)" class="action-btn text-[var(--status-red-fg)]" @click="triggerCancel(msg)" :disabled="busyName === msg.name" title="Cancel Broadcast">
                  <FeatherIcon name="x-circle" class="w-3.5 h-3.5" />
                </button>
                <button v-if="msg.docstatus === 0" class="action-btn" @click="editDraft(msg)" title="Edit draft">
                  <FeatherIcon name="edit" class="w-3.5 h-3.5" />
                </button>
                <button class="action-btn" @click="duplicateBroadcast(msg)" title="Duplicate">
                  <FeatherIcon name="copy" class="w-3.5 h-3.5" />
                </button>
                <button class="action-btn text-[var(--status-red-fg)]" @click="triggerDelete(msg)" title="Delete">
                  <FeatherIcon name="trash-2" class="w-3.5 h-3.5" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Bulk Delete Confirmation -->
    <ConfirmDialog
      :open="showBulkDeleteConfirm"
      :title="`Delete ${selectedNames.length} Broadcast${selectedNames.length > 1 ? 's' : ''}?`"
      message="Are you sure you want to delete the selected bulk message campaigns? This action cannot be undone."
      confirm="Delete Broadcasts"
      cancel="Keep Broadcasts"
      tone="danger"
      :busy="isBulkDeleting"
      busy-label="Deleting..."
      @confirm="confirmBulkDelete"
      @cancel="showBulkDeleteConfirm = false"
    />

    <!-- Delete Confirmation -->
    <ConfirmDialog
      :open="showDeleteConfirm"
      title="Delete Broadcast?"
      message="Are you sure you want to delete this bulk message campaign? This will remove all records for it. This action cannot be undone."
      confirm="Delete Broadcast"
      cancel="Keep Broadcast"
      tone="danger"
      :busy="isDeleting"
      busy-label="Deleting..."
      @confirm="confirmDelete"
      @cancel="showDeleteConfirm = false"
    />

    <!-- Cancel Confirmation -->
    <ConfirmDialog
      :open="showCancelConfirm"
      title="Cancel Broadcast?"
      message="Sends already in flight will finish, but no further recipients will be messaged. This cannot be undone."
      confirm="Cancel Broadcast"
      cancel="Keep Running"
      tone="danger"
      :busy="busyName === cancelTargetName"
      busy-label="Cancelling..."
      @confirm="confirmCancel"
      @cancel="showCancelConfirm = false"
    />

    <!-- Detail Drawer Overlay -->
    <Transition name="drawer-fade">
      <div v-if="showDrawer" class="detail-drawer-overlay" @click.self="closeDrawer">
        <div class="detail-drawer">
          <!-- Drawer Header -->
          <div class="drawer-header">
            <div class="drawer-title-area">
              <h2 class="drawer-title">{{ activeBroadcast?.title || activeBroadcast?.name }}</h2>
              <span class="drawer-subtitle">{{ activeBroadcast?.name }}</span>
            </div>
            <button class="btn-close-drawer" @click="closeDrawer">
              <FeatherIcon name="x" class="w-4 h-4" />
            </button>
          </div>

          <!-- Drawer Tabs -->
          <div class="drawer-tabs">
            <button
              class="drawer-tab"
              :class="{ active: activeTab === 'overview' }"
              @click="activeTab = 'overview'"
            >
              Overview
            </button>
            <button
              class="drawer-tab"
              :class="{ active: activeTab === 'analytics' }"
              @click="activeTab = 'analytics'"
            >
              Analytics
            </button>
          </div>

          <!-- Drawer Body -->
          <div class="drawer-body">
            <!-- 1. Overview Tab -->
            <div v-if="activeTab === 'overview'" class="overview-grid">
              <div class="info-section">
                <h3 class="info-section-title">Broadcast Info</h3>
                <div class="info-row">
                  <span class="info-label">Status</span>
                  <StatusPill :status="activeBroadcast?.status || 'Draft'" />
                </div>
                <div class="info-row" v-if="activeBroadcast?.whatsapp_account">
                  <span class="info-label">WABA Account</span>
                  <span class="info-value">{{ activeBroadcast.whatsapp_account }}</span>
                </div>
                <div class="info-row" v-if="activeBroadcast?.template">
                  <span class="info-label">Template</span>
                  <span class="info-value font-mono">{{ activeBroadcast.template }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Audience Type</span>
                  <span class="info-value">{{ activeBroadcast?.recipient_type }}</span>
                </div>
                <div class="info-row" v-if="activeBroadcast?.recipient_list">
                  <span class="info-label">Recipient List</span>
                  <span class="info-value">{{ activeBroadcast.recipient_list }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">Total Recipients</span>
                  <span class="info-value">{{ activeBroadcast?.recipient_count || 0 }}</span>
                </div>
                <div class="info-row" v-if="activeBroadcast?.scheduled_time">
                  <span class="info-label">Scheduled Time</span>
                  <span class="info-value">{{ formatDate(activeBroadcast.scheduled_time, true) }}</span>
                </div>
                <div class="info-row" v-if="activeBroadcast?.creation">
                  <span class="info-label">Created At</span>
                  <span class="info-value">{{ formatDate(activeBroadcast.creation, true) }}</span>
                </div>
                <div class="info-row" v-if="activeBroadcast?.modified">
                  <span class="info-label">Last Synced</span>
                  <span class="info-value">{{ formatDate(activeBroadcast.modified, true) }}</span>
                </div>
              </div>

              <!-- Live Progress Stats Card -->
              <div class="info-section">
                <h3 class="info-section-title">Delivery Progress</h3>
                <Shimmer v-if="progressLoading && !progressDetail" class="shm-pad" variant="rows" :count="6" />
                <div v-else-if="progressDetail" class="stats-bars-list">
                  <!-- Progress Bar Fill -->
                  <div class="stat-bar-item">
                    <div class="stat-bar-header">
                      <span class="text-[var(--text-secondary)]">Succeeded Sending</span>
                      <span class="text-[var(--text-primary)] font-semibold">{{ progressDetail.percent }}%</span>
                    </div>
                    <div class="stat-bar-fill-wrap">
                      <div
                        class="stat-bar-fill bg-emerald-500"
                        :style="{ width: progressDetail.percent + '%' }"
                      ></div>
                    </div>
                  </div>

                  <!-- Count Metrics Table -->
                  <div class="counts-metrics-grid mt-4">
                    <div class="metric-mini-card">
                      <span class="mmc-dot bg-slate-400"></span>
                      <span class="mmc-val">{{ progressDetail.queued || 0 }}</span>
                      <span class="mmc-lbl">Queued</span>
                    </div>
                    <div class="metric-mini-card">
                      <span class="mmc-dot bg-blue-500"></span>
                      <span class="mmc-val">{{ progressDetail.sent || 0 }}</span>
                      <span class="mmc-lbl">Sent</span>
                    </div>
                    <div class="metric-mini-card">
                      <span class="mmc-dot bg-[var(--brand)]"></span>
                      <span class="mmc-val">{{ progressDetail.delivered || 0 }}</span>
                      <span class="mmc-lbl">Delivered</span>
                    </div>
                    <div class="metric-mini-card">
                      <span class="mmc-dot bg-emerald-500"></span>
                      <span class="mmc-val">{{ progressDetail.read || 0 }}</span>
                      <span class="mmc-lbl">Read</span>
                    </div>
                    <div class="metric-mini-card">
                      <span class="mmc-dot bg-rose-500"></span>
                      <span class="mmc-val">{{ progressDetail.failed || 0 }}</span>
                      <span class="mmc-lbl">Failed</span>
                    </div>
                    <div class="metric-mini-card">
                      <span class="mmc-dot bg-slate-300"></span>
                      <span class="mmc-val">{{ progressDetail.pending || 0 }}</span>
                      <span class="mmc-lbl">Pending</span>
                    </div>
                  </div>

                  <div v-if="progressDetail.retry_count" class="text-xs text-[var(--status-amber-fg)] mt-2 font-medium">
                    <Icon name="alert-triangle" :size="14" class="ei" /> Retried failed recipients {{ progressDetail.retry_count }} time(s).
                  </div>
                </div>
              </div>

              <!-- Delivery + engagement metrics (exact vs template-level attribution) -->
              <div v-if="activeBroadcast?.name" class="info-section">
                <h3 class="info-section-title">Performance</h3>
                <BroadcastMetricsCard :broadcast="activeBroadcast.name" />
              </div>

              <!-- Template Preview Card -->
              <div class="info-section">
                <div class="flex items-center justify-between mb-3">
                  <h3 class="info-section-title mb-0">Template Preview</h3>
                  <span v-if="activeBroadcast?.template" class="text-xs font-mono text-[var(--text-secondary)] px-2 py-0.5 bg-[var(--bg-sunken)] rounded">
                    {{ activeBroadcast.template }}
                  </span>
                </div>

                <Shimmer v-if="templateLoading" variant="rows" :count="4" />

                <div v-else-if="templateDoc" class="wa-preview-bubble-container">
                  <div class="wa-chat-bg">
                    <div class="wa-message-bubble">
                      <!-- Header (Media or Text) -->
                      <div v-if="templateDoc.header_type === 'MEDIA' || templateDoc.header_type === 'IMAGE' || templateDoc.header_type === 'DOCUMENT' || templateDoc.header_type === 'VIDEO'" class="wa-bubble-media">
                        <div class="wa-media-placeholder">
                          <FeatherIcon :name="getMediaIcon(templateDoc.header_type)" class="w-5 h-5 text-[var(--ink-500)]" />
                          <span class="text-xs text-[var(--ink-600)] font-medium ml-2 uppercase">{{ templateDoc.header_type }} HEADER</span>
                        </div>
                      </div>
                      <div v-else-if="templateDoc.header" class="wa-bubble-header">
                        {{ formatTemplateText(templateDoc.header) }}
                      </div>

                      <!-- Body Text -->
                      <div class="wa-bubble-body">
                        {{ formatTemplateText(templateDoc.template) }}
                      </div>

                      <!-- Footer Text -->
                      <div v-if="templateDoc.footer" class="wa-bubble-footer">
                        {{ formatTemplateText(templateDoc.footer) }}
                      </div>

                      <!-- Timestamp indicator -->
                      <div class="wa-bubble-time">
                        12:00 PM <span class="text-emerald-500 ml-1"><Icon name="check" :size="14" class="ei" /><Icon name="check" :size="14" class="ei" /></span>
                      </div>

                      <!-- Interactive Action Buttons -->
                      <div v-if="getTemplateButtons(templateDoc).length" class="wa-bubble-buttons">
                        <div
                          v-for="(btn, idx) in getTemplateButtons(templateDoc)"
                          :key="idx"
                          class="wa-bubble-btn"
                        >
                          <FeatherIcon :name="getButtonIcon(btn.button_type)" class="w-3.5 h-3.5 mr-1.5 text-sky-600" />
                          <span>{{ btn.button_label || btn.text || 'Button' }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-else class="text-xs text-[var(--text-tertiary)] py-2">
                  No template preview available
                </div>
              </div>

              <!-- Quick actions in drawer -->
              <div class="info-section">
                <h3 class="info-section-title">Actions</h3>
                <div class="drawer-actions-row">
                  <button v-if="activeBroadcast && canRetry(activeBroadcast)" class="btn-drawer-action bg-[var(--status-amber-bg)] text-[var(--status-amber-fg)] hover:bg-[var(--status-amber-bg)]" @click="retryBroadcast(activeBroadcast)" :disabled="busyName === activeBroadcast.name">
                    <FeatherIcon name="refresh-cw" class="w-3.5 h-3.5" />
                    <span>Retry Failed</span>
                  </button>
                  <button v-if="activeBroadcast && canPause(activeBroadcast)" class="btn-drawer-action bg-[var(--status-blue-bg)] text-[var(--status-blue-fg)] hover:bg-[var(--status-blue-bg)]" @click="pauseBroadcast(activeBroadcast)" :disabled="busyName === activeBroadcast.name">
                    <FeatherIcon name="pause" class="w-3.5 h-3.5" />
                    <span>Pause</span>
                  </button>
                  <button v-if="activeBroadcast && canResume(activeBroadcast)" class="btn-drawer-action bg-[var(--status-green-bg)] text-[var(--status-green-fg)] hover:bg-[var(--status-green-bg)]" @click="resumeBroadcast(activeBroadcast)" :disabled="busyName === activeBroadcast.name">
                    <FeatherIcon name="play" class="w-3.5 h-3.5" />
                    <span>Resume</span>
                  </button>
                  <button v-if="activeBroadcast && canCancel(activeBroadcast)" class="btn-drawer-action bg-[var(--status-red-bg)] text-[var(--status-red-fg)] hover:bg-[var(--status-red-bg)]" @click="triggerCancel(activeBroadcast)" :disabled="busyName === activeBroadcast.name">
                    <FeatherIcon name="x-circle" class="w-3.5 h-3.5" />
                    <span>Cancel Campaign</span>
                  </button>
                  <button v-if="activeBroadcast && activeBroadcast.docstatus === 0" class="btn-drawer-action bg-[var(--bg-sunken)] text-[var(--text-primary)] hover:bg-[var(--bg-sunken)]" @click="editDraft(activeBroadcast)">
                    <FeatherIcon name="edit" class="w-3.5 h-3.5" />
                    <span>Edit draft</span>
                  </button>
                  <button v-if="activeBroadcast" class="btn-drawer-action bg-[var(--bg-sunken)] text-[var(--text-primary)] hover:bg-[var(--bg-sunken)]" @click="duplicateBroadcast(activeBroadcast)">
                    <FeatherIcon name="copy" class="w-3.5 h-3.5" />
                    <span>Duplicate</span>
                  </button>
                  <button v-if="activeBroadcast" class="btn-drawer-action bg-[var(--status-red-bg)] text-[var(--status-red-fg)] hover:bg-[var(--status-red-bg)]" @click="triggerDelete(activeBroadcast)">
                    <FeatherIcon name="trash-2" class="w-3.5 h-3.5" />
                    <span>Delete</span>
                  </button>
                </div>
              </div>
            </div>

            <!-- 2. Analytics Tab -->
            <div v-else-if="activeTab === 'analytics'" class="analytics-tab-wrap">
              <div class="analytics-filters">
                <!-- Search row -->
                <div class="analytics-search-row">
                  <div class="search-input-wrapper">
                    <FeatherIcon name="search" class="search-icon-inline" />
                    <input
                      type="text"
                      class="form-input search-input-inline-box"
                      v-model="logsSearch"
                      placeholder="Search name or number…"
                      @input="handleSearchInput"
                    />
                  </div>
                  <button class="btn-export-inline" @click="exportRecipients">
                    <FeatherIcon name="download" class="w-3.5 h-3.5 mr-1" />
                    Export
                  </button>
                </div>

                <!-- Status Tabs -->
                <div class="analytics-status-tabs">
                  <button
                    class="analytics-status-btn"
                    :class="{ active: logsStatus === 'all' }"
                    @click="setLogStatus('all')"
                  >
                    All
                  </button>
                  <button
                    class="analytics-status-btn"
                    :class="{ active: logsStatus === 'queued' }"
                    @click="setLogStatus('queued')"
                  >
                    Queued
                  </button>
                  <button
                    class="analytics-status-btn"
                    :class="{ active: logsStatus === 'sent' }"
                    @click="setLogStatus('sent')"
                  >
                    Sent
                  </button>
                  <button
                    class="analytics-status-btn"
                    :class="{ active: logsStatus === 'delivered' }"
                    @click="setLogStatus('delivered')"
                  >
                    Delivered
                  </button>
                  <button
                    class="analytics-status-btn"
                    :class="{ active: logsStatus === 'read' }"
                    @click="setLogStatus('read')"
                  >
                    Read
                  </button>
                  <button
                    class="analytics-status-btn"
                    :class="{ active: logsStatus === 'failed' }"
                    @click="setLogStatus('failed')"
                  >
                    Failed
                  </button>
                </div>
              </div>

              <!-- Logs Table -->
              <Shimmer v-if="logsLoading" class="shm-pad" variant="rows" :count="6" />

              <div v-else-if="logs.length === 0" class="logs-empty-state">
                <FeatherIcon name="inbox" class="w-8 h-8 text-[var(--text-tertiary)]" />
                <p>No recipient logs match your filter.</p>
              </div>

              <template v-else>
                <div class="logs-table-wrapper">
                  <table class="logs-table">
                    <thead>
                      <tr>
                        <th>Recipient</th>
                        <th>Status</th>
                        <th>Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="log in logs" :key="log.name">
                        <td>
                          <div class="log-recipient-info">
                            <span class="log-recipient-name font-medium">{{ log.recipient_name || '—' }}</span>
                            <span class="log-recipient-phone font-mono text-xs text-[var(--text-secondary)] block mt-0.5">{{ log.mobile_number || '—' }}</span>
                          </div>
                        </td>
                        <td>
                          <div class="log-status-wrap">
                            <span
                              class="log-status-badge"
                              :class="'status-' + (log.status || '').toLowerCase()"
                            >
                              {{ log.status }}
                            </span>
                            <!-- Show error if failed -->
                            <p
                              v-if="log.status === 'failed' && (log.failure_reason || log.status_error)"
                              class="log-error-text"
                              :title="log.failure_reason || log.status_error"
                            >
                              {{ log.failure_reason || log.status_error }}
                            </p>
                          </div>
                        </td>
                        <td class="log-cell-time">
                          {{ formatDate(log.modified, true) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <!-- Logs Pager -->
                <div v-if="logsTotal > 50" class="logs-pager">
                  <button
                    class="pager-btn"
                    :disabled="logsPage === 1"
                    @click="changeLogsPage(logsPage - 1)"
                  >
                    <FeatherIcon name="chevron-left" class="w-4 h-4" />
                  </button>
                  <span class="pager-info">
                    Page {{ logsPage }} / {{ Math.ceil(logsTotal / 50) }}
                  </span>
                  <button
                    class="pager-btn"
                    :disabled="logsPage * 50 >= logsTotal"
                    @click="changeLogsPage(logsPage + 1)"
                  >
                    <FeatherIcon name="chevron-right" class="w-4 h-4" />
                  </button>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { FeatherIcon, toast } from 'frappe-ui'
import { prettifyFrappeError } from '@/shared/utils/storeHelpers'
import { useWhatsApp } from '@/modules/whatsapp/store/whatsapp'
import PageHeader from '@/shared/ui/PageHeader.vue'
import KpiCard from '@/shared/ui/KpiCard.vue'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'
import StatusPill from '@/shared/ui/StatusPill.vue'
import BroadcastMetricsCard from '@/modules/whatsapp/components/BroadcastMetricsCard.vue'
import { callRpc } from '@/services/_factory'

const store = useWhatsApp()
const router = useRouter()

function startNewBroadcast() {
  try {
    sessionStorage.removeItem('wa_broadcast_wizard_default')
  } catch (_) {}
  router.push({ name: 'WhatsAppBroadcastWizard' })
}

const selectedNames = ref([])
const showBulkDeleteConfirm = ref(false)
const isBulkDeleting = ref(false)

const isAllSelected = computed(() => {
  const list = store.bulkMessages || []
  return list.length > 0 && list.every((m) => selectedNames.value.includes(m.name))
})

const isIndeterminate = computed(() => {
  const list = store.bulkMessages || []
  if (!list.length) return false
  const count = list.filter((m) => selectedNames.value.includes(m.name)).length
  return count > 0 && count < list.length
})

function toggleSelectAll() {
  const list = store.bulkMessages || []
  if (isAllSelected.value) {
    selectedNames.value = []
  } else {
    selectedNames.value = list.map((m) => m.name)
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

const statusFilters = [
  { value: 'all', label: 'All' },
  { value: 'Draft', label: 'Draft', dot: 'var(--ink-300)' },
  { value: 'Scheduled', label: 'Scheduled', dot: '#eab308' },
  { value: 'In Progress', label: 'In Progress', dot: '#3b82f6' },
  { value: 'Completed', label: 'Completed', dot: '#22c55e' },
  { value: 'Partially Failed', label: 'Failed', dot: '#ef4444' },
  { value: 'Cancelled', label: 'Cancelled', dot: 'var(--ink-300)' },
]

const busyName = ref('')
const progressDetail = ref(null)
const progressLoading = ref(false)
let progressTimer = null

const showCancelConfirm = ref(false)
const cancelTargetName = ref('')

// Side Drawer State
const showDrawer = ref(false)
const activeBroadcast = ref(null)
const activeTab = ref('overview') // 'overview' | 'analytics'

const logs = ref([])
const logsLoading = ref(false)
const logsTotal = ref(0)
const logsPage = ref(1)
const logsStatus = ref('all')
const logsSearch = ref('')

const templateDoc = ref(null)
const templateLoading = ref(false)

async function fetchBulkMessages() {
  await store.fetchBulkMessages()
}

async function setStatusFilter(status) {
  store.bulkFilters.status = status
  await fetchBulkMessages()
}

async function viewBroadcast(name) {
  const msg = store.bulkMessages.find((m) => m.name === name)
  if (!msg) return

  activeBroadcast.value = msg
  showDrawer.value = true
  activeTab.value = 'overview'
  progressDetail.value = null
  templateDoc.value = null

  if (msg.template) {
    loadTemplateDoc(msg.template)
  }

  await loadProgress(name)
  startProgressPolling(name)

  // Initialize analytics variables
  logsPage.value = 1
  logsStatus.value = 'all'
  logsSearch.value = ''
  logs.value = []
  logsTotal.value = 0

  await fetchLogs()
}

async function loadTemplateDoc(templateName) {
  templateLoading.value = true
  try {
    const doc = await callRpc('frappe.client.get', {
      doctype: 'WhatsApp Templates',
      name: templateName,
    })
    templateDoc.value = doc
  } catch (e) {
    console.error('Failed to load template doc:', e)
    templateDoc.value = null
  } finally {
    templateLoading.value = false
  }
}

function getMediaIcon(headerType) {
  if (headerType === 'IMAGE') return 'image'
  if (headerType === 'VIDEO') return 'video'
  if (headerType === 'DOCUMENT') return 'file-text'
  return 'file'
}

function getButtonIcon(type) {
  if (type === 'Call Phone' || type === 'PHONE_NUMBER') return 'phone'
  if (type === 'Visit Website' || type === 'URL') return 'external-link'
  if (type === 'Quick Reply' || type === 'QUICK_REPLY') return 'corner-up-left'
  if (type === 'Catalog' || type === 'CATALOG') return 'shopping-bag'
  return 'message-square'
}

function getTemplateButtons(doc) {
  if (!doc) return []
  if (Array.isArray(doc.buttons) && doc.buttons.length) return doc.buttons
  if (doc.button_configuration) {
    try {
      const parsed = typeof doc.button_configuration === 'string' ? JSON.parse(doc.button_configuration) : doc.button_configuration
      return parsed.buttons || []
    } catch (e) {
      return []
    }
  }
  return []
}

function formatTemplateText(txt) {
  if (!txt) return ''
  return txt.replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, '{$1}')
}

async function fetchLogs() {
  if (!activeBroadcast.value) return
  logsLoading.value = true
  try {
    const res = await callRpc(
      'msuite_whatsapp.api.v1.app.crud.get_bulk_message_logs',
      {
        bulk_message: activeBroadcast.value.name,
        status: logsStatus.value,
        search: logsSearch.value,
        start: (logsPage.value - 1) * 50,
        page_length: 50,
      }
    )
    logs.value = res?.rows || []
    logsTotal.value = res?.total || 0
  } catch (e) {
    console.error('Failed to fetch bulk message logs', e)
  } finally {
    logsLoading.value = false
  }
}

async function setLogStatus(status) {
  logsStatus.value = status
  logsPage.value = 1
  await fetchLogs()
}

async function changeLogsPage(page) {
  logsPage.value = page
  await fetchLogs()
}

let searchTimeout = null
function handleSearchInput() {
  if (searchTimeout) clearTimeout(searchTimeout)
  if (!logsSearch.value) {
    logsPage.value = 1
    fetchLogs()
  } else {
    searchTimeout = setTimeout(async () => {
      logsPage.value = 1
      await fetchLogs()
    }, 300)
  }
}

async function exportRecipients() {
  if (!activeBroadcast.value) return
  try {
    const res = await callRpc(
      'msuite_whatsapp.api.v1.app.crud.get_bulk_message_logs',
      {
        bulk_message: activeBroadcast.value.name,
        status: logsStatus.value,
        search: logsSearch.value,
        start: 0,
        page_length: 100000,
      }
    )
    const rows = res?.rows || []
    if (!rows.length) {
      toast.info('No data to export')
      return
    }

    const headers = ['Recipient Name', 'Mobile Number', 'Status', 'Failure Reason', 'Modified Time']
    const csvRows = [headers.join(',')]

    for (const r of rows) {
      const name = (r.recipient_name || '').replace(/"/g, '""')
      const phone = r.mobile_number || ''
      const status = r.status || ''
      const error = (r.status_error || r.failure_reason || '').replace(/"/g, '""')
      const time = r.modified || ''

      csvRows.push(`"${name}","${phone}","${status}","${error}","${time}"`)
    }

    const csvContent = '\uFEFF' + csvRows.join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.setAttribute('href', url)
    link.setAttribute('download', `${activeBroadcast.value.title || 'broadcast'}_recipients_export.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } catch (e) {
    console.error('Failed to export recipients', e)
    toast.error(prettifyFrappeError(e) || 'Failed to export recipients')
  }
}

function closeDrawer() {
  showDrawer.value = false
  activeBroadcast.value = null
  stopProgressPolling()
}

watch(activeTab, (newTab) => {
  if (newTab === 'analytics') {
    fetchLogs()
  }
})

async function loadProgress(name) {
  progressLoading.value = true
  try {
    progressDetail.value = await store.fetchBulkProgress(name)
  } catch (e) {
    console.error('Failed to fetch broadcast progress', e)
    progressDetail.value = null
  } finally {
    progressLoading.value = false
  }
}

function startProgressPolling(name) {
  stopProgressPolling()
  const msg = store.bulkMessages.find((m) => m.name === name)
  if (!msg || (msg.status !== 'In Progress' && msg.status !== 'Queued')) return
  progressTimer = setInterval(async () => {
    if (!showDrawer.value || activeBroadcast.value?.name !== name) {
      stopProgressPolling()
      return
    }
    await loadProgress(name)
    if (activeTab.value === 'analytics') {
      await fetchLogs()
    }
  }, 8000)
}

function stopProgressPolling() {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
}

function duplicateBroadcast(msg) {
  router.push({ name: 'WhatsAppBroadcastWizard', query: { duplicate: msg.name } })
}

// Reopen a saved draft in the wizard; its saves/send update this same record.
function editDraft(msg) {
  router.push({ name: 'WhatsAppBroadcastWizard', query: { draft: msg.name } })
}

function triggerDelete(msg) {
  deleteTargetName.value = msg.name
  showDeleteConfirm.value = true
}

async function confirmDelete() {
  isDeleting.value = true
  try {
    await store.deleteBulkMessage(deleteTargetName.value)
    showDeleteConfirm.value = false
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'Broadcast deleted.', indicator: 'green' })
    }
  } catch (e) {
    console.error('Failed to delete broadcast', e)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({ message: 'Failed to delete broadcast.', indicator: 'red' })
    }
  } finally {
    isDeleting.value = false
  }
}

async function confirmBulkDelete() {
  if (!selectedNames.value.length) return
  isBulkDeleting.value = true
  try {
    const res = await store.bulkDeleteBulkMessages(selectedNames.value)
    showBulkDeleteConfirm.value = false
    const count = res?.deleted?.length || selectedNames.value.length
    selectedNames.value = []
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({
        message: `Deleted ${count} broadcast${count > 1 ? 's' : ''} successfully.`,
        indicator: 'green',
      })
    }
  } catch (e) {
    console.error('Failed to bulk delete broadcasts', e)
    if (window.frappe?.show_alert) {
      window.frappe.show_alert({
        message: e?.message || 'Failed to bulk delete broadcasts.',
        indicator: 'red',
      })
    }
  } finally {
    isBulkDeleting.value = false
  }
}

function getStatusClass(status) {
  if (!status) return 'draft'
  const s = status.toLowerCase()
  if (s.includes('progress') || s === 'queued') return 'progress'
  if (s === 'scheduled') return 'scheduled'
  if (s === 'completed') return 'completed'
  if (s === 'cancelled') return 'cancelled'
  if (s.includes('fail') || s.includes('reject')) return 'failed'
  return 'draft'
}

function getSuccessPercent(msg) {
  if (!msg.recipient_count) return 0
  return Math.round(((msg.sent_count || 0) / msg.recipient_count) * 100)
}

function getFailedPercent(msg) {
  if (!msg.recipient_count) return 0
  return Math.round(((msg.failed_count || 0) / msg.recipient_count) * 100)
}

function canPause(msg) {
  return (msg.status === 'In Progress' || msg.status === 'Queued') && !msg.is_paused
}

function canResume(msg) {
  return (msg.status === 'In Progress' || msg.status === 'Queued') && msg.is_paused
}

function canCancel(msg) {
  return !['Completed', 'Cancelled'].includes(msg.status)
}

function canRetry(msg) {
  return msg.status === 'Partially Failed' || msg.status === 'AWS Dispatch Failed'
}

function notify(message, indicator = 'green') {
  if (window.frappe?.show_alert) {
    window.frappe.show_alert({ message, indicator })
  }
}

async function pauseBroadcast(msg) {
  busyName.value = msg.name
  try {
    await store.pauseBulkMessage(msg.name)
    notify('Broadcast paused.', 'blue')
  } catch (e) {
    console.error('Failed to pause broadcast', e)
    notify('Failed to pause broadcast.', 'red')
  } finally {
    busyName.value = ''
  }
}

async function resumeBroadcast(msg) {
  busyName.value = msg.name
  try {
    await store.resumeBulkMessage(msg.name)
    notify('Broadcast resumed.', 'blue')
    if (expandedName.value === msg.name) await loadProgress(msg.name)
  } catch (e) {
    console.error('Failed to resume broadcast', e)
    notify('Failed to resume broadcast.', 'red')
  } finally {
    busyName.value = ''
  }
}

async function retryBroadcast(msg) {
  busyName.value = msg.name
  try {
    const requeued = await store.retryBulkMessage(msg.name)
    notify(requeued ? `${requeued} message(s) re-queued for retry.` : 'No failed messages to retry.', requeued ? 'blue' : 'orange')
    if (expandedName.value === msg.name) await loadProgress(msg.name)
  } catch (e) {
    console.error('Failed to retry broadcast', e)
    notify('Failed to retry broadcast.', 'red')
  } finally {
    busyName.value = ''
  }
}

function triggerCancel(msg) {
  cancelTargetName.value = msg.name
  showCancelConfirm.value = true
}

async function confirmCancel() {
  const name = cancelTargetName.value
  busyName.value = name
  try {
    await store.cancelBulkMessage(name)
    notify('Broadcast cancelled.', 'blue')
    showCancelConfirm.value = false
  } catch (e) {
    console.error('Failed to cancel broadcast', e)
    notify('Failed to cancel broadcast.', 'red')
  } finally {
    busyName.value = ''
  }
}

function formatDate(dt, includeTime = false) {
  if (!dt) return ''
  const d = new Date(dt)
  if (Number.isNaN(d.getTime())) return ''
  
  const dateStr = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  if (includeTime) {
    const timeStr = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    return `${dateStr}, ${timeStr}`
  }
  return dateStr
}

onMounted(async () => {
  await Promise.all([store.fetchBulkMetrics(), store.fetchBulkMessages()])
})

onUnmounted(() => {
  stopProgressPolling()
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

/* Advanced Filters */
.filters-bar { display: flex; align-items: flex-end; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.filters-left { display: flex; gap: 12px; flex-wrap: wrap; }
.filter-select-wrapper { display: flex; flex-direction: column; gap: 4px; }
.filter-lbl { font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em; }
.filter-select { height: 36px; padding: 0 10px; border: 1.5px solid var(--border-base); border-radius: 8px; font-size: 13px; color: var(--text-primary); background: var(--surface-surface); outline: none; min-width: 150px; }
.filter-select:focus { border-color: var(--brand-color); }
.btn-clear-filters { height: 36px; padding: 0 14px; border: 1.5px solid var(--border-base); border-radius: 8px; background: var(--surface-surface); font-size: 12px; font-weight: 500; color: var(--text-secondary); cursor: pointer; }
.btn-clear-filters:hover { border-color: var(--ink-200); color: var(--text-primary); }

.custom-dates-bar { margin-bottom: 16px; }
.custom-date-inputs { display: flex; align-items: center; gap: 8px; }
.date-input { height: 36px; padding: 0 10px; border: 1.5px solid var(--border-base); border-radius: 8px; font-size: 13px; color: var(--text-primary); background: var(--surface-surface); }
.to-separator { font-size: 13px; color: var(--text-tertiary); }

/* Loading / Empty */
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

/* Table */
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

.template-tag { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 500; padding: 3px 8px; border-radius: 6px; background: var(--state-success-bg); border: 1.5px solid var(--state-success-border); color: var(--state-success); }
.audience-info { display: flex; flex-direction: column; }
.actions-col { width: 120px; text-align: right; }
.row-actions { display: flex; align-items: center; gap: 4px; justify-content: flex-end; }
.action-btn { width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border: none; background: transparent; border-radius: 6px; color: var(--text-secondary); cursor: pointer; transition: background 0.1s, color 0.1s; }
.action-btn:hover { background: var(--border-soft); color: var(--text-primary); }
.action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.text-rose-600 { color: var(--state-danger); }
.action-btn.text-rose-600:hover { background: var(--state-danger-bg); color: var(--state-danger); }
.action-btn.text-amber-600:hover { background: var(--state-warning-bg); color: var(--state-warning); }

/* Status Cells & Progress Bars */
.status-cell { display: flex; flex-direction: column; gap: 6px; }
.progress-bar-container { display: flex; flex-direction: column; gap: 4px; width: 100%; min-width: 150px; }
.progress-bar-bg { height: 6px; width: 100%; border-radius: 3px; background: var(--border-soft); overflow: hidden; display: flex; }
.progress-bar-fill { height: 100%; transition: width 0.3s ease; }
.progress-bar-success { background: var(--state-success, #22c55e); }
.progress-bar-warning { background: var(--state-warning, #eab308); }
.progress-bar-danger { background: var(--state-danger, #ef4444); }
.progress-text { font-size: var(--fs-2xs); color: var(--text-secondary); font-weight: 500; display: flex; flex-wrap: wrap; align-items: center; }

/* Detail Drawer Overlay & Slide Transition */
.detail-drawer-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(15, 23, 42, 0.4);
  backdrop-filter: blur(2px);
  z-index: 100;
  display: flex;
  justify-content: flex-end;
}
.detail-drawer {
  width: 580px;
  max-width: 90vw;
  background: var(--surface-surface, var(--bg-surface));
  height: 100%;
  display: flex;
  flex-direction: column;
  box-shadow: -6px 0 30px rgba(15, 23, 42, 0.18);
  border-left: 1px solid var(--border-base);
}

.drawer-fade-enter-active, .drawer-fade-leave-active {
  transition: opacity 0.25s ease;
}
.drawer-fade-enter-from, .drawer-fade-leave-to {
  opacity: 0;
}
.drawer-fade-enter-active .detail-drawer, .drawer-fade-leave-active .detail-drawer {
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.drawer-fade-enter-from .detail-drawer, .drawer-fade-leave-to .detail-drawer {
  transform: translateX(100%);
}

/* Header */
.drawer-header {
  padding: 22px 24px;
  border-bottom: 1px solid var(--border-base);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  background: var(--surface-surface);
}
.drawer-title-area {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.drawer-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.drawer-subtitle {
  font-size: 11px;
  font-family: monospace;
  color: var(--text-tertiary);
}
.btn-close-drawer {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid var(--border-base);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.12s;
}
.btn-close-drawer:hover {
  background: var(--border-soft);
  color: var(--text-primary);
}

/* Tabs */
.drawer-tabs {
  display: flex;
  border-bottom: 1px solid var(--border-base);
  background: var(--surface-page, var(--ink-25));
  padding: 0 16px;
}
.drawer-tab {
  padding: 12px 20px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  border: none;
  background: transparent;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all 0.12s;
  outline: none;
}
.drawer-tab:hover {
  color: var(--text-primary);
}
.drawer-tab.active {
  color: var(--brand-500);
  border-bottom-color: var(--brand-500);
}

/* Body */
.drawer-body {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 24px;
}

/* Overview section cards */
.overview-grid {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.info-section {
  background: var(--surface-page, var(--ink-25));
  border: 1px solid var(--border-soft, #eef2ff);
  border-radius: 12px;
  padding: 18px;
}
.info-section-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
  margin-bottom: 12px;
  margin-top: 0;
}
.info-row {
  display: flex;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-soft, var(--ink-50));
  font-size: 13px;
}
.info-row:last-child {
  border-bottom: none;
}
.info-label {
  color: var(--text-secondary);
  font-weight: 500;
}
.info-value {
  color: var(--text-primary);
  font-weight: 600;
}

/* Stats Progress bars inside Overview */
.stats-bars-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.stat-bar-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.stat-bar-header {
  display: flex;
  justify-content: space-between;
  font-size: 12.5px;
  font-weight: 500;
}
.stat-bar-fill-wrap {
  height: 8px;
  border-radius: 4px;
  background: var(--border-soft, var(--ink-50));
  overflow: hidden;
}
.stat-bar-fill {
  height: 100%;
  border-radius: 4px;
}

/* Counts Metrics Grid */
.counts-metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.metric-mini-card {
  background: var(--surface-surface);
  border: 1px solid var(--border-soft, #eef2ff);
  border-radius: 8px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  position: relative;
}
.mmc-dot {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.mmc-val {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}
.mmc-lbl {
  font-size: var(--fs-2xs);
  font-weight: 500;
  color: var(--text-secondary);
  margin-top: 2px;
}

/* Actions block in drawer */
.drawer-actions-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.btn-drawer-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 38px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: background 0.12s, transform 0.08s;
}
.btn-drawer-action:active {
  transform: translateY(1px);
}
.btn-drawer-action:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Analytics Tab Elements */
.analytics-tab-wrap {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.analytics-filters {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 18px;
}
.analytics-search-row {
  display: flex;
  gap: 8px;
}
.search-input-wrapper {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
}
.search-icon-inline {
  position: absolute;
  left: 10px;
  width: 14px;
  height: 14px;
  color: var(--text-tertiary);
  pointer-events: none;
}
.search-input-inline-box {
  height: 36px;
  width: 100%;
  padding: 0 12px 0 32px;
  border: 1.5px solid var(--border-base);
  border-radius: 8px;
  font-size: 12.5px;
  outline: none;
}
.search-input-inline-box:focus {
  border-color: var(--brand-color);
}
.btn-export-inline {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  padding: 0 14px;
  border-radius: 8px;
  border: 1px solid var(--border-base);
  background: var(--surface-surface);
  color: var(--text-secondary);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.btn-export-inline:hover {
  background: var(--border-soft);
  color: var(--text-primary);
  border-color: var(--border-medium);
}

.analytics-status-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.analytics-status-btn {
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  border: 1px solid var(--border-base);
  background: var(--surface-surface);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.12s;
}
.analytics-status-btn:hover {
  border-color: var(--text-secondary);
  color: var(--text-primary);
}
.analytics-status-btn.active {
  background: var(--brand);
  color: var(--text-on-brand);
  border-color: var(--brand-500);
}

/* Logs loading / empty */
.logs-loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  color: var(--text-secondary);
  font-size: 13px;
}
.logs-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}
.logs-empty-state p {
  margin: 8px 0 0;
  font-size: 13px;
}

/* Logs Table */
.logs-table-wrapper {
  border: 1px solid var(--border-base);
  border-radius: 10px;
  overflow-x: auto;
  overflow-y: hidden;
  max-height: 480px;
  overflow-y: auto;
}
.logs-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.logs-table thead tr {
  position: sticky;
  top: 0;
  background: var(--surface-page, var(--ink-25));
  z-index: 1;
}
.logs-table th {
  text-align: left;
  padding: 8px 12px;
  font-size: var(--fs-2xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-base);
}
.logs-table td {
  padding: 8px 12px;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-soft, var(--ink-50));
  vertical-align: top;
}
.logs-table tbody tr:last-child td {
  border-bottom: none;
}
.logs-table tbody tr:hover td {
  background: var(--surface-page, var(--ink-25));
}
.log-cell-phone {
  font-weight: 500;
}
.log-cell-time {
  color: var(--text-secondary);
  font-size: 11.5px;
  white-space: nowrap;
}

/* Logs status badge mapping */
.log-status-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.log-status-badge {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: var(--fs-2xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.log-status-badge.status-queued {
  background: var(--ink-50);
  color: var(--ink-500);
}
.log-status-badge.status-sent {
  background: var(--status-blue-bg);
  color: #1e90ff;
}
.log-status-badge.status-delivered {
  background: var(--status-blue-bg);
  color: var(--status-blue-fg);
}
.log-status-badge.status-read {
  background: var(--status-green-bg);
  color: var(--green-700);
}
.log-status-badge.status-failed {
  background: var(--status-red-bg);
  color: var(--danger);
}
.log-error-text {
  font-size: var(--fs-2xs);
  color: var(--danger);
  margin: 0;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Logs Pager */
.logs-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 12px 14px;
  border-top: 1px solid var(--border-base);
  background: var(--surface-page, var(--ink-25));
  margin-top: 12px;
  border-radius: 8px;
}

/* Utility color classes */
.text-slate-800 { color: var(--ink-800); } .text-slate-600 { color: var(--ink-600); } .text-slate-500 { color: var(--ink-500); }
.text-slate-700 { color: var(--ink-700); }
.text-emerald-600 { color: var(--status-green-fg); } .text-amber-600 { color: var(--status-amber-fg); } .text-rose-600 { color: var(--status-red-fg); }
.text-blue-600 { color: var(--status-blue-fg); }
.text-brand-500 { color: var(--brand); } .text-emerald-500 { color: var(--emerald-500); } .text-amber-500 { color: var(--orange-500); }
.text-rose-500 { color: var(--rose-500); } .text-slate-400 { color: var(--ink-300); }
.bg-emerald-50 { background-color: var(--status-green-bg); } .bg-amber-50 { background-color: var(--status-amber-bg); }
.bg-rose-50 { background-color: var(--status-red-bg); } .bg-slate-50 { background-color: var(--ink-25); }
.bg-blue-50 { background-color: var(--status-blue-bg); }
.font-medium { font-weight: 500; }

/* WhatsApp Bubble Preview in Drawer */
.wa-preview-bubble-container {
  border: 1px solid var(--ink-100);
  border-radius: 12px;
  max-height: 400px;
  overflow-y: auto;
  overflow-x: hidden;
  background-color: #efeae2;
  background-image: radial-gradient(#d1d7db 1px, transparent 1px);
  background-size: 16px 16px;
  padding: 14px;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.25) transparent;
}
.wa-preview-bubble-container::-webkit-scrollbar {
  width: 6px;
}
.wa-preview-bubble-container::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
}
.wa-preview-bubble-container::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.25);
  border-radius: 4px;
}
.wa-preview-bubble-container::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.4);
}
.wa-chat-bg {
  display: flex;
  justify-content: flex-start;
}
.wa-message-bubble {
  max-width: 92%;
  background: #ffffff;
  border-radius: 0px 8px 8px 8px;
  padding: 10px 12px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
  position: relative;
}
.wa-media-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 75px;
  background: #f0f2f5;
  border-radius: 6px;
  margin-bottom: 8px;
  border: 1px dashed var(--ink-200);
}
.wa-bubble-header {
  font-weight: 700;
  font-size: 13px;
  color: var(--ink-900, #111827);
  margin-bottom: 4px;
}
.wa-bubble-body {
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--ink-800, #1f2937);
  white-space: pre-wrap;
  word-break: break-word;
}
.wa-bubble-footer {
  font-size: 11px;
  color: var(--ink-400, #9ca3af);
  margin-top: 6px;
}
.wa-bubble-time {
  font-size: var(--fs-2xs);
  color: var(--ink-400, #9ca3af);
  text-align: right;
  margin-top: 4px;
}
.wa-bubble-buttons {
  border-top: 1px solid #e9edef;
  margin-top: 8px;
  padding-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wa-bubble-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px 10px;
  background: #ffffff;
  border: 1px solid #e9edef;
  border-radius: 6px;
  color: #00a884;
  font-size: 11.5px;
  font-weight: 600;
}
</style>
