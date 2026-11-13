<template>
  <div class="wa-insights-page">
    <!-- Top Header -->
    <PageHeader
      :title="currentAccountInfo?.account_name || currentAccountInfo?.name || 'WhatsApp Account'"
      :subtitle="currentAccountInfo ? `WABA ID: ${currentAccountInfo.waba_id}${currentAccountInfo.phone_number ? ' · Phone: ' + currentAccountInfo.phone_number : ''}` : 'WhatsApp Manager Insights'"
    >
      <template #meta>
        <div class="flex items-center gap-2">
          <span class="status-dot-active" title="Account Status: Active"></span>

          <!-- Account Switcher Dropdown -->
          <div class="account-switcher" v-if="accountsList.length > 1">
            <select v-model="selectedAccount" @change="fetchInsights" class="l-input h-8 text-xs py-1">
              <option v-for="acc in accountsList" :key="acc.name" :value="acc.name">
                {{ acc.account_name || acc.name }} ({{ acc.waba_id }})
              </option>
            </select>
          </div>
        </div>
      </template>

      <template #actions>
        <button class="l-btn l-btn--secondary" @click="triggerRefresh" :disabled="refreshing">
          <FeatherIcon name="refresh-cw" class="w-4 h-4" :class="{ 'animate-spin': refreshing }" />
          <span>{{ refreshing ? 'Syncing...' : 'Sync Meta Insights' }}</span>
        </button>
      </template>
    </PageHeader>

    <!-- Top Tabs & Filters Bar -->
    <div class="control-tabs-bar">
      <div class="main-tabs">
        <button 
          class="tab-btn" 
          :class="{ active: activeTab === 'pricing' }" 
          @click="activeTab = 'pricing'"
        >
          Message pricing
        </button>
        <button 
          class="tab-btn" 
          :class="{ active: activeTab === 'overview' }" 
          @click="activeTab = 'overview'"
        >
          Performance overview
        </button>
        <button 
          class="tab-btn" 
          :class="{ active: activeTab === 'calling' }" 
          @click="activeTab = 'calling'"
        >
          Calling pricing
        </button>
      </div>

      <div class="filters-row">
        <!-- Phone Filter -->
        <select v-model="selectedPhone" class="filter-select">
          <option value="all">All phone numbers</option>
          <option v-if="currentAccountInfo?.phone_number" :value="currentAccountInfo.phone_number">
            {{ currentAccountInfo.phone_number }}
          </option>
        </select>

        <!-- Country Filter -->
        <select v-model="selectedCountry" class="filter-select">
          <option value="all">All countries</option>
          <option value="IN">India (+91)</option>
        </select>

        <!-- Date Range Filter -->
        <select v-model="selectedDays" @change="fetchInsights" class="filter-select date-select">
          <option :value="7">Last 7 days: {{ dateRangeLabel(7) }}</option>
          <option :value="14">Last 14 days: {{ dateRangeLabel(14) }}</option>
          <option :value="30">Last 30 days: {{ dateRangeLabel(30) }}</option>
          <option :value="90">Last 90 days: {{ dateRangeLabel(90) }}</option>
        </select>
      </div>
    </div>

    <!-- Notice Banner -->
    <div class="notice-banner">
      <FeatherIcon name="info" class="w-4 h-4 text-blue-500 shrink-0" />
      <span>Note: All insights data is approximate and may differ from what is shown on your invoices due to small variations in data processing.</span>
    </div>

    <!-- Loading State -->
    <Shimmer v-if="loading" variant="rows" :count="5" />

    <!-- TAB 1: MESSAGE PRICING -->
    <div v-else-if="activeTab === 'pricing'" class="tab-content">
      <!-- 5 Key Metric Cards Grid -->
      <div class="insights-cards-grid">
        <!-- Card 1: All messages -->
        <div class="insight-card">
          <div class="card-header-line">
            <h3 class="card-title">All messages</h3>
          </div>
          <div class="card-metric-rows">
            <div class="metric-row">
              <span class="row-label">Messages sent</span>
              <span class="row-value">{{ totals.all_messages?.sent || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Messages delivered</span>
              <span class="row-value">{{ totals.all_messages?.delivered || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Messages received</span>
              <span class="row-value">{{ totals.all_messages?.received || 0 }}</span>
            </div>
          </div>
        </div>

        <!-- Card 2: Messages delivered -->
        <div class="insight-card">
          <div class="card-header-line">
            <h3 class="card-title">Messages delivered</h3>
            <span class="total-badge">{{ totals.delivered_by_category?.total || 0 }}</span>
          </div>
          <div class="card-metric-rows">
            <div class="metric-row">
              <span class="row-label">Marketing</span>
              <span class="row-value">{{ totals.delivered_by_category?.marketing || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Marketing - lite</span>
              <span class="row-value">{{ countOrNa(totals.delivered_by_category?.marketing_lite) }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Utility</span>
              <span class="row-value">{{ totals.delivered_by_category?.utility || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Authentication</span>
              <span class="row-value">{{ totals.delivered_by_category?.authentication || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Authentication - international</span>
              <span class="row-value">{{ totals.delivered_by_category?.authentication_international || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">AI provider</span>
              <span class="row-value">{{ totals.delivered_by_category?.ai_provider || 0 }}</span>
            </div>
            <div class="metric-row font-medium">
              <span class="row-label">Service</span>
              <span class="row-value">{{ totals.delivered_by_category?.service || 0 }}</span>
            </div>
          </div>
        </div>

        <!-- Card 3: Free messages delivered -->
        <div class="insight-card">
          <div class="card-header-line">
            <h3 class="card-title">Free messages delivered</h3>
            <span class="total-badge">{{ totals.free_messages?.total || 0 }}</span>
          </div>
          <div class="card-metric-rows">
            <div class="metric-row">
              <span class="row-label">Free customer service</span>
              <span class="row-value">{{ totals.free_messages?.free_customer_service || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Free entry point</span>
              <span class="row-value">{{ totals.free_messages?.free_entry_point || 0 }}</span>
            </div>
          </div>
        </div>

        <!-- Card 4: Paid messages delivered -->
        <div class="insight-card">
          <div class="card-header-line">
            <h3 class="card-title">Paid messages delivered</h3>
            <span class="total-badge">{{ totals.paid_messages?.total || 0 }}</span>
          </div>
          <div class="card-metric-rows">
            <div class="metric-row">
              <span class="row-label">Marketing</span>
              <span class="row-value">{{ totals.paid_messages?.marketing || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Marketing - lite</span>
              <span class="row-value">{{ countOrNa(totals.paid_messages?.marketing_lite) }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Utility</span>
              <span class="row-value">{{ totals.paid_messages?.utility || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Authentication</span>
              <span class="row-value">{{ totals.paid_messages?.authentication || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Authentication - international</span>
              <span class="row-value">{{ totals.paid_messages?.authentication_international || 0 }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">AI provider</span>
              <span class="row-value">{{ totals.paid_messages?.ai_provider || 0 }}</span>
            </div>
          </div>
        </div>

        <!-- Card 5: Approximate total charges -->
        <div class="insight-card highlight-card">
          <div class="card-header-line">
            <h3 class="card-title">Approximate total charges</h3>
            <span class="total-charges-value">
              {{ currencySymbol(totals.approximate_charges?.currency) }}{{ formatPrice(totals.approximate_charges?.total) }}
            </span>
          </div>
          <div class="card-metric-rows">
            <div class="metric-row">
              <span class="row-label">Marketing</span>
              <span class="row-value">{{ currencySymbol(totals.approximate_charges?.currency) }}{{ formatPrice(totals.approximate_charges?.marketing) }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Marketing - lite</span>
              <span class="row-value">{{ chargeOrNa(totals.approximate_charges?.marketing_lite, currencySymbol(totals.approximate_charges?.currency)) }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Utility</span>
              <span class="row-value">{{ currencySymbol(totals.approximate_charges?.currency) }}{{ formatPrice(totals.approximate_charges?.utility) }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Authentication</span>
              <span class="row-value">{{ currencySymbol(totals.approximate_charges?.currency) }}{{ formatPrice(totals.approximate_charges?.authentication) }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">Authentication - international</span>
              <span class="row-value">{{ currencySymbol(totals.approximate_charges?.currency) }}{{ formatPrice(totals.approximate_charges?.authentication_international) }}</span>
            </div>
            <div class="metric-row">
              <span class="row-label">AI provider</span>
              <span class="row-value">{{ currencySymbol(totals.approximate_charges?.currency) }}{{ formatPrice(totals.approximate_charges?.ai_provider) }}</span>
            </div>
          </div>
        </div>
      </div>

      <MarketingMessagesPanel
        :account="selectedAccount"
        :days="selectedDays"
        :reload-token="panelReloadToken"
      />

      <!-- Chart 1: Messages Delivered Trend -->
      <div class="chart-box">
        <div class="chart-header flex justify-between items-center mb-4">
          <div>
            <h3 class="chart-title">Messages delivered</h3>
            <p class="chart-sub">Daily message volume split over selected timeframe</p>
          </div>
        </div>
        <div class="chart-container">
          <svg class="trend-svg" viewBox="0 0 800 220" preserveAspectRatio="none">
            <!-- Grid lines -->
            <line x1="0" y1="40" x2="800" y2="40" stroke="var(--border-subtle, #e5e7eb)" stroke-dasharray="4" />
            <line x1="0" y1="100" x2="800" y2="100" stroke="var(--border-subtle, #e5e7eb)" stroke-dasharray="4" />
            <line x1="0" y1="160" x2="800" y2="160" stroke="var(--border-subtle, #e5e7eb)" stroke-dasharray="4" />
            
            <!-- Delivered Line Path -->
            <path :d="chartDeliveredPath" fill="none" stroke="#059669" stroke-width="2.5" />
            <!-- Received Line Path -->
            <path :d="chartReceivedPath" fill="none" stroke="var(--brand)" stroke-width="2.5" stroke-dasharray="5 5" />
          </svg>
          <div class="chart-x-labels">
            <span v-for="(item, idx) in dailyTrend" :key="idx" class="x-label">
              {{ formatDateShort(item.date) }}
            </span>
          </div>
        </div>
        <div class="chart-legend flex gap-6 justify-center mt-3 text-xs">
          <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-full bg-emerald-600"></span> Messages Delivered</span>
          <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-full bg-[var(--brand)]"></span> Messages Received</span>
        </div>
      </div>
    </div>

    <!-- TAB 2: PERFORMANCE OVERVIEW -->
    <div v-else-if="activeTab === 'overview'" class="tab-content">
      <div class="overview-grid">
        <div class="summary-card">
          <span class="label">Total Sent</span>
          <span class="val">{{ totals.all_messages?.sent || 0 }}</span>
        </div>
        <div class="summary-card">
          <span class="label">Total Delivered</span>
          <span class="val text-emerald-600">{{ totals.all_messages?.delivered || 0 }}</span>
        </div>
        <div class="summary-card">
          <span class="label">Delivery Rate</span>
          <span class="val text-emerald-600">
            {{ totals.all_messages?.sent ? Math.round((totals.all_messages.delivered / totals.all_messages.sent) * 100) : 100 }}%
          </span>
        </div>
        <div class="summary-card">
          <span class="label">Messages Received</span>
          <span class="val text-blue-600">{{ totals.all_messages?.received || 0 }}</span>
        </div>
      </div>

      <!-- Template Performance Table -->
      <div class="table-card mt-6">
        <h3 class="table-title">Template Performance</h3>
        <div class="l-table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th class="l-th">Template Name</th>
                <th class="l-th">Category</th>
                <th class="l-th">Sent</th>
                <th class="l-th">Delivered</th>
                <th class="l-th">Read %</th>
                <th class="l-th">Clicked</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!templatePerformance.length">
                <td colspan="6" class="text-center py-6 text-[var(--ink-500)]">No template metrics recorded for this timeframe yet.</td>
              </tr>
              <tr v-for="(tpl, idx) in templatePerformance" :key="idx">
                <td class="font-medium">{{ tpl.name || tpl.template_name }}</td>
                <td><span class="category-badge">{{ templateCategoryLabel(tpl.category) }}</span></td>
                <td>{{ tpl.sent || 0 }}</td>
                <td>{{ tpl.delivered || 0 }}</td>
                <td>{{ tpl.read_rate || 0 }}%</td>
                <td>{{ tpl.clicked || 0 }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 3: CALLING PRICING -->
    <div v-else-if="activeTab === 'calling'" class="tab-content">
      <div class="calling-card">
        <h3 class="card-title">WhatsApp In-App Calling Usage</h3>
        <p class="text-sm text-[var(--text-secondary)] mt-1">Calling metrics and permission request usage for WhatsApp In-App Voice Calling.</p>
        
        <div class="calling-stats-grid mt-6">
          <div class="stat-box">
            <span class="stat-lbl">Call Permission Requests</span>
            <span class="stat-val">0</span>
          </div>
          <div class="stat-box">
            <span class="stat-lbl">Voice Calls Received</span>
            <span class="stat-val">0</span>
          </div>
          <div class="stat-box">
            <span class="stat-lbl">Total Duration</span>
            <span class="stat-val">00m 00s</span>
          </div>
          <div class="stat-box">
            <span class="stat-lbl">Calling Charges</span>
            <span class="stat-val">₹0.00</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { createResource } from 'frappe-ui'
import { FeatherIcon } from 'frappe-ui'
import PageHeader from '@/shared/ui/PageHeader.vue'
import { templateCategoryLabel, countOrNa, chargeOrNa } from './insightsHelpers.js'
import MarketingMessagesPanel from '../components/MarketingMessagesPanel.vue'

const route = useRoute()

const props = defineProps({
  account: { type: String, default: '' }
})

const activeTab = ref('pricing')
const selectedAccount = ref(props.account || '')
const selectedDays = ref(7)
const selectedPhone = ref('all')
const selectedCountry = ref('all')
const refreshing = ref(false)
const loading = ref(true)
// Bumped on every insights (re)load so the Marketing Messages panel reloads with it.
const panelReloadToken = ref(0)

const currentAccountInfo = ref(null)
const accountsList = ref([])
const totals = ref({})
const dailyTrend = ref([])
const templatePerformance = ref([])
const errorBreakdown = ref([])

function dateRangeLabel(days) {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - days)
  return `${formatDateShort(start)} - ${formatDateShort(end)}`
}

function formatDateShort(dateInput) {
  if (!dateInput) return ''
  const d = new Date(dateInput)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function currencySymbol(curr) {
  if (curr === 'INR') return '₹'
  if (curr === 'USD') return '$'
  if (curr === 'EUR') return '€'
  return curr ? `${curr} ` : '₹'
}

function formatPrice(val) {
  if (val === undefined || val === null) return '0.00'
  return floatValue(val).toFixed(2)
}

function floatValue(val) {
  const num = parseFloat(val)
  return isNaN(num) ? 0.0 : num
}

const insightsResource = createResource({
  url: 'msuite_whatsapp.api.v1.app.analytics_query.get_whatsapp_account_insights',
  makeParams() {
    return {
      account_name: selectedAccount.value || props.account || 'all',
      days: selectedDays.value
    }
  },
  onSuccess(data) {
    loading.value = false
    if (!data) return
    currentAccountInfo.value = data.account
    accountsList.value = data.accounts_list || []
    if (data.account && !selectedAccount.value) {
      selectedAccount.value = data.account.name
    }
    totals.value = data.totals || {}
    dailyTrend.value = data.daily_trend || []
    templatePerformance.value = data.template_performance || []
    errorBreakdown.value = data.error_breakdown || []
  },
  onError(err) {
    loading.value = false
    console.error('Failed to load WhatsApp Insights:', err)
  }
})

const refreshResource = createResource({
  url: 'msuite_whatsapp.api.v1.app.analytics_sync.refresh_account_analytics',
  onSuccess() {
    refreshing.value = false
    fetchInsights()
  },
  onError(err) {
    refreshing.value = false
    console.error('Failed to refresh Meta analytics:', err)
  }
})

function fetchInsights() {
  loading.value = true
  panelReloadToken.value += 1
  insightsResource.fetch()
}

function triggerRefresh() {
  if (!selectedAccount.value) return
  refreshing.value = true
  refreshResource.submit({ account_name: selectedAccount.value })
}

// SVG Chart Builders
const chartDeliveredPath = computed(() => {
  if (!dailyTrend.value.length) return 'M 0 110 L 800 110'
  const maxVal = Math.max(...dailyTrend.value.map(d => d.delivered || 0), 10)
  const pts = dailyTrend.value.map((d, i) => {
    const x = (i / Math.max(dailyTrend.value.length - 1, 1)) * 800
    const y = 200 - ((d.delivered || 0) / maxVal) * 160
    return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
  })
  return pts.join(' ')
})

const chartReceivedPath = computed(() => {
  if (!dailyTrend.value.length) return 'M 0 110 L 800 110'
  const maxVal = Math.max(...dailyTrend.value.map(d => Math.max(d.delivered || 0, d.received || 0)), 10)
  const pts = dailyTrend.value.map((d, i) => {
    const x = (i / Math.max(dailyTrend.value.length - 1, 1)) * 800
    const y = 200 - ((d.received || 0) / maxVal) * 160
    return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
  })
  return pts.join(' ')
})

watch(() => props.account, (newVal) => {
  if (newVal) {
    selectedAccount.value = newVal
    fetchInsights()
  }
})

onMounted(() => {
  fetchInsights()
})
</script>

<style scoped>
.wa-insights-page {
  padding: 0;
  min-height: 100vh;
}

.insights-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.25rem;
}

.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--text-tertiary, var(--ink-500));
  margin-bottom: 0.5rem;
}

.breadcrumbs .active {
  font-weight: 500;
  color: var(--text-primary, var(--ink-900));
}

.account-title-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.account-name {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary, var(--ink-900));
}

.status-dot-active {
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 50%;
  background-color: #10b981;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
}

.account-switcher select {
  padding: 0.25rem 0.625rem;
  font-size: 0.875rem;
  border-radius: 0.375rem;
  border: 1px solid var(--border-subtle, var(--ink-200));
  background-color: var(--bg-card, var(--bg-surface));
}

.account-meta-text {
  font-size: 0.8125rem;
  color: var(--text-tertiary, var(--ink-500));
  margin-top: 0.25rem;
}

.btn-secondary {
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: 0.375rem;
  border: 1px solid var(--border-subtle, var(--ink-200));
  background-color: var(--bg-card, var(--bg-surface));
  cursor: pointer;
  transition: background 0.15s;
}

.btn-secondary:hover {
  background-color: var(--bg-hover, var(--ink-50));
}

.control-tabs-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border-subtle, var(--ink-100));
  padding-bottom: 0.75rem;
  margin-bottom: 1rem;
}

.main-tabs {
  display: flex;
  gap: 1.5rem;
}

.tab-btn {
  font-size: 0.9375rem;
  font-weight: 500;
  color: var(--text-tertiary, var(--ink-500));
  padding-bottom: 0.75rem;
  border-bottom: 2px solid transparent;
  background: none;
  border-top: none;
  border-left: none;
  border-right: none;
  cursor: pointer;
}

.tab-btn.active {
  color: #047857;
  border-bottom-color: #047857;
  font-weight: 600;
}

.filters-row {
  display: flex;
  gap: 0.75rem;
}

.filter-select {
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
  border-radius: 0.375rem;
  border: 1px solid var(--border-subtle, var(--ink-200));
  background-color: var(--bg-card, var(--bg-surface));
  color: var(--text-primary, var(--ink-700));
}

.notice-banner {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.625rem 1rem;
  background-color: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 0.375rem;
  font-size: 0.8125rem;
  color: #1e40af;
  margin-bottom: 1.5rem;
}

/* Insights 5-Card Grid */
.insights-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1.25rem;
  margin-bottom: 2rem;
}

.insight-card {
  background-color: var(--bg-card, var(--bg-surface));
  border: 1px solid var(--border-subtle, var(--ink-100));
  border-radius: 0.5rem;
  padding: 1.125rem;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}

.highlight-card {
  border-color: #a7f3d0;
  background: linear-gradient(180deg, #ecfdf5 0%, var(--bg-surface) 100%);
}

.card-header-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border-subtle, #f3f4f6);
  padding-bottom: 0.625rem;
  margin-bottom: 0.75rem;
}

.card-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary, var(--ink-900));
}

.total-badge {
  font-size: 0.875rem;
  font-weight: 700;
  color: #047857;
}

.total-charges-value {
  font-size: 1.125rem;
  font-weight: 700;
  color: #047857;
}

.card-metric-rows {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.8125rem;
}

.row-label {
  color: var(--text-tertiary, var(--ink-500));
}

.row-value {
  font-weight: 600;
  color: var(--text-primary, var(--ink-900));
}

/* Charts */
.chart-box {
  background-color: var(--bg-card, var(--bg-surface));
  border: 1px solid var(--border-subtle, var(--ink-100));
  border-radius: 0.5rem;
  padding: 1.25rem;
}

.chart-title {
  font-size: 1rem;
  font-weight: 600;
}

.chart-sub {
  font-size: 0.8125rem;
  color: var(--text-tertiary, var(--ink-500));
}

.chart-container {
  width: 100%;
  position: relative;
}

.trend-svg {
  width: 100%;
  height: 220px;
}

.chart-x-labels {
  display: flex;
  justify-content: space-between;
  padding-top: 0.5rem;
  font-size: 0.75rem;
  color: var(--text-tertiary, var(--ink-400));
}

/* Overview Tab */
.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.25rem;
}

.summary-card {
  background: var(--bg-card, var(--bg-surface));
  border: 1px solid var(--border-subtle, var(--ink-100));
  border-radius: 0.5rem;
  padding: 1.25rem;
}

.summary-card .label {
  font-size: 0.8125rem;
  color: var(--text-tertiary, var(--ink-500));
  display: block;
}

.summary-card .val {
  font-size: 1.5rem;
  font-weight: 700;
  margin-top: 0.375rem;
  display: block;
}

/* Data Table */
.table-card {
  background: var(--bg-card, var(--bg-surface));
  border: 1px solid var(--border-subtle, var(--ink-100));
  border-radius: 0.5rem;
  padding: 1.25rem;
}

.table-title {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 1rem;
}

.data-table {
  width: 100%;
  text-align: left;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.data-table th {
  padding: 0.625rem 0.875rem;
  border-bottom: 1px solid var(--border-subtle, var(--ink-100));
  color: var(--text-tertiary, var(--ink-500));
  font-weight: 500;
}

.data-table td {
  padding: 0.75rem 0.875rem;
  border-bottom: 1px solid var(--border-subtle, #f3f4f6);
}

.category-badge {
  padding: 0.125rem 0.5rem;
  border-radius: 0.25rem;
  background-color: var(--ink-50);
  font-size: 0.75rem;
  font-weight: 500;
}

.calling-card {
  background: var(--bg-card, var(--bg-surface));
  border: 1px solid var(--border-subtle, var(--ink-100));
  border-radius: 0.5rem;
  padding: 1.5rem;
}

.calling-stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.25rem;
}

.stat-box {
  padding: 1rem;
  background-color: var(--bg-surface, var(--ink-25));
  border-radius: 0.375rem;
  border: 1px solid var(--border-subtle, #f3f4f6);
}

.stat-lbl {
  font-size: 0.8125rem;
  color: var(--text-tertiary, var(--ink-500));
  display: block;
}

.stat-val {
  font-size: 1.25rem;
  font-weight: 700;
  margin-top: 0.25rem;
  display: block;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 0;
  color: var(--text-tertiary, var(--ink-500));
}

.spinner {
  width: 2rem;
  height: 2rem;
  border: 3px solid var(--ink-100);
  border-top-color: #047857;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 1rem;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
