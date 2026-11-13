<!--
  WhatsAppDashboard — WhatsApp Messaging Command Center.
  Based on lemnia_ui WhatsAppOverview.vue reference layout.

  Sections:
  1. Header with period switcher (7d / month / qtr) and New broadcast action
  2. Deliverability & engagement KPI strip (KpiCard)
  3. Hero: Messages by purpose (Marketing / Utility / Authentication) + AivoInsight
  4. Grid: Delivery health funnel + Account standing (no block/opt-out row)
  5. Aivo account-health diagnostics (rule-based facts)
  6. Recent broadcasts table at the bottom (Table)

  All numbers come from live backend calculations via
  `msuite_whatsapp.api.v1.app.accounts.get_dashboard_metrics`.
-->
<template>
  <div class="dash">
    <!-- Header -->
    <PageHeader
      title="WhatsApp performance"
      :subtitle="`${formatNumber(summary.sent)} sent · ${formatNumber(summary.recipients)} recipients · ${summary.lists || 0} lists · ${summary.quality || 'Unknown'} quality rating`"
    >
      <template #actions>
        <div class="flex items-center gap-2">
          <div class="l-segment" role="group" aria-label="Period filter">
            <button
              type="button"
              class="seg-btn"
              :class="{ 'is-active': selectedPeriod === '7d' }"
              @click="setPeriod('7d')"
            >
              7 days
            </button>
            <button
              type="button"
              class="seg-btn"
              :class="{ 'is-active': selectedPeriod === 'month' }"
              @click="setPeriod('month')"
            >
              This month
            </button>
            <button
              type="button"
              class="seg-btn"
              :class="{ 'is-active': selectedPeriod === 'qtr' }"
              @click="setPeriod('qtr')"
            >
              Quarter
            </button>
          </div>
          <button
            type="button"
            class="l-btn l-btn--primary"
            @click="openNewBroadcast"
          >
            <Icon name="plus" :size="15" />
            <span>New broadcast</span>
          </button>
        </div>
      </template>
    </PageHeader>

    <!-- Error message if overview fails -->
    <ErrorState
      v-if="store.dashboardError"
      title="Could not load WhatsApp metrics"
      :message="store.dashboardError"
      :retry="() => store.fetchDashboardOverview(selectedPeriod)"
    />

    <!-- Loading skeleton -->
    <div v-if="store.dashboardLoading && !summary.sent && !categoryRollup.length" class="wdash-loading">
      <div v-for="n in 6" :key="n" class="skeleton skeleton-kpi" />
    </div>

    <template v-else>
      <!-- KPI strip — deliverability & engagement -->
      <div class="l-metrics">
        <KpiCard
          label="Messages sent"
          :value="formatNumber(summary.sent)"
          icon="send"
          :delta="periodSubText"
        />

        <KpiCard
          label="Delivered"
          :value="summary.deliveredPct != null ? `${summary.deliveredPct}%` : '—'"
          icon="check-circle"
          :bar="summary.deliveredPct"
          bar-color="var(--accent-teal, #14B8A6)"
          :delta="`${formatNumber(summary.delivered)} messages`"
        />

        <KpiCard
          label="Read"
          :value="summary.readPct != null ? `${summary.readPct}%` : '—'"
          icon="eye"
          :delta="readDelta ? readDelta.text : ''"
          :delta-tone="readDelta ? readDelta.tone : ''"
        />

        <KpiCard
          label="Reply rate"
          :value="summary.replyPct != null ? `${summary.replyPct}%` : '—'"
          icon="message-circle"
          :delta="replyDelta ? replyDelta.text : `${formatNumber(summary.replied)} conversations`"
          :delta-tone="replyDelta ? replyDelta.tone : 'up'"
        />

        <KpiCard
          label="Sender quality"
          :value="summary.quality || 'Unknown'"
          icon="shield"
          :delta="summary.tier ? `Messaging tier: ${summary.tier}` : 'Account standing'"
          :delta-tone="qualityDeltaTone"
        />

        <KpiCard
          label="Approved templates"
          :value="summary.templatesApproved ?? 0"
          :small="` / ${summary.templatesTotal ?? 0}`"
          icon="file-text"
          :delta="`${summary.templatesRejected ?? 0} rejected · ${summary.templatesPending ?? 0} pending`"
          :delta-tone="summary.templatesRejected > 0 ? 'down' : ''"
        />
      </div>

      <!-- Hero: Messages by purpose + Aivo -->
      <div class="grid-hero">
        <div class="panel">
          <div class="card-h">
            <h3>Messages by purpose</h3>
            <span class="sub">each judged on its own goal</span>
          </div>
          <div v-for="p in categoryPurposes" :key="p.key" class="pur">
            <div class="pur-row">
              <div class="pur-ic" :style="{ background: p.color }">
                <Icon :name="p.icon" :size="17" />
              </div>
              <div class="pur-meta">
                <div class="pur-name">{{ p.name }}</div>
                <div class="pur-desc">{{ p.desc }}</div>
              </div>
              <div class="pur-vol">
                <div class="pv tnum">{{ formatNumber(p.volume) }}</div>
                <div class="pl">messages</div>
              </div>
              <div class="pur-out">
                <div class="po" :style="{ color: p.warn ? 'var(--warning, #F59E0B)' : 'var(--success, #10B981)' }">
                  {{ p.metric }}
                </div>
                <div class="pos">{{ p.metricSub }}</div>
              </div>
            </div>
            <div class="pur-bar">
              <i :style="{ width: `${p.pct}%`, background: p.barColor }" />
            </div>
          </div>
        </div>

        <AivoInsight
          :kicker="aivoFacts.kicker || 'Account health'"
          :title="aivoFacts.title"
          :coming-soon="false"
        >
          {{ aivoFacts.summary }}
          <template v-if="aivoFacts.stats && aivoFacts.stats.length" #stats>
            <div v-for="st in aivoFacts.stats" :key="st.label" class="lai-stat">
              <span class="dot" :style="{ background: st.dotColor }" />
              <span>{{ st.label }}</span>
              <span class="amt">{{ st.value }}</span>
            </div>
          </template>
          <template #actions>
            <button
              type="button"
              class="btn-ai-action"
              @click="$router.push({ name: 'WhatsAppBulkMessages' })"
            >
              See broadcasts
            </button>
          </template>
        </AivoInsight>
      </div>

      <!-- Delivery health + Account standing -->
      <div class="grid-2">
        <div class="panel">
          <div class="card-h">
            <h3>Delivery health</h3>
            <span class="sub">all messages · {{ periodSubText }}</span>
          </div>
          <div class="dfun">
            <div v-for="d in deliveryFunnel" :key="d.name" class="dfun-row">
              <span class="dl">{{ d.name }}</span>
              <div class="dfun-track">
                <div
                  class="dfun-fill"
                  :style="{
                    width: `${d.pct != null ? Math.max(4, d.pct) : 0}%`,
                    background: d.color,
                    color: d.dark ? '#ffffff' : '#15181D',
                  }"
                >
                  {{ formatNumber(d.count) }}
                </div>
              </div>
              <div class="dfun-pct">
                <template v-if="d.pct != null">
                  {{ d.pct }}%
                  <small>{{ d.name === 'Sent' ? '' : 'of sent' }}</small>
                </template>
                <template v-else>
                  —
                </template>
              </div>
            </div>
          </div>
          <div class="dfun-foot">
            <div class="big tnum">{{ formatNumber(deliveryHealth.conversations_opened || summary.replied) }}</div>
            <div class="fl">
              <b>conversations opened</b> from replies in this period<br>
              <template v-if="(deliveryHealth.reply_rate ?? summary.replyPct) != null">
                a {{ deliveryHealth.reply_rate ?? summary.replyPct }}% reply rate
              </template>
              <template v-else>
                no reply rate yet (nothing sent in this period)
              </template>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="card-h">
            <h3>Account standing</h3>
            <span class="sub">as reported by Meta</span>
          </div>
          <div class="health">
            <div class="h-row">
              <div class="h-k">
                <span class="gi"><Icon name="shield" :size="13" /></span>
                <span>Quality rating</span>
              </div>
              <span class="pill" :class="qualityPillClass">
                {{ summary.quality || 'Unknown' }}
              </span>
            </div>
            <div class="h-row">
              <div class="h-k">
                <span class="gi"><Icon name="send" :size="13" /></span>
                <span>Messaging tier</span>
              </div>
              <div class="h-v">
                {{ standing.tier || summary.tier || '—' }}
                <span class="tier-unit">/ day</span>
              </div>
            </div>
            <div class="h-row hcol">
              <div class="h-k">
                <span class="gi"><Icon name="file-text" :size="13" /></span>
                <span>Template approvals</span>
              </div>
              <div class="tmpls">
                <span v-for="t in standingTemplates" :key="t.label" class="tmpl">
                  <span class="dot" :style="{ background: t.dot }" />
                  <span class="num">{{ t.n }}</span>
                  <span>{{ t.label }}</span>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Aivo Account Health Diagnosis (Facts & issues) -->
      <div v-if="aivoFacts.has_issues && aivoFacts.issues && aivoFacts.issues.length" class="aicard">
        <div class="aicard-h">
          <div class="aicard-k">
            <Icon name="sparkles" :size="13" />
            <span>Account health diagnosis</span>
          </div>
          <div class="aicard-t">{{ aivoFacts.title }}</div>
        </div>
        <div class="aicard-body">
          <div v-for="(iss, i) in aivoFacts.issues" :key="i" class="issue">
            <span class="dchip" :class="iss.severity">
              <Icon :name="iss.chipIcon || 'alert-circle'" :size="12" />
              <span>{{ iss.chip }}</span>
            </span>
            <div class="issue-when">{{ iss.when }}</div>
            <div class="issue-t">{{ iss.title }}</div>
            <div class="issue-why" v-html="iss.why" />

            <div v-if="iss.rejects && iss.rejects.length" class="rej">
              <div v-for="r in iss.rejects" :key="r.name" class="rej-row">
                <div class="rej-top">
                  <span class="rej-name">{{ r.name }}</span>
                  <span class="rej-reason">{{ r.reason }}</span>
                </div>
                <div class="rej-fix" v-html="r.fix" />
              </div>
            </div>

            <template v-else-if="iss.fixes && iss.fixes.length">
              <div class="fix-h">{{ iss.fixH || 'Recommended fixes' }}</div>
              <ul class="fix">
                <li v-for="(f, fi) in iss.fixes" :key="fi" v-html="f" />
              </ul>
            </template>
          </div>
        </div>
        <div class="aicard-src">
          <Icon name="sparkles" :size="12" />
          <span>Real-time Meta account diagnostics and delivery verification</span>
        </div>
      </div>

      <!-- Recent Broadcasts (bottom table) -->
      <div class="panel">
        <div class="card-h">
          <div>
            <h3>Recent broadcasts</h3>
            <span class="sub">sent &amp; scheduled</span>
          </div>
          <button
            type="button"
            class="view-all-link"
            @click="$router.push({ name: 'WhatsAppBulkMessages' })"
          >
            View all →
          </button>
        </div>

        <Table
          :columns="broadcastColumns"
          :rows="recentBroadcasts"
          row-key="name"
          :empty="{ title: 'No broadcasts found', description: 'Schedule or send your first bulk message campaign to start messaging customers.' }"
        >
          <template #cell-title="{ row }">
            <div class="nm-wrap" @click="openBroadcast(row)">
              <div class="nm">{{ row.title || row.name }}</div>
              <div class="co">{{ row.template || 'No template' }}</div>
            </div>
          </template>

          <template #cell-purpose="{ row }">
            <span class="tag">{{ row.purpose || 'Marketing' }}</span>
          </template>

          <template #cell-status="{ row }">
            <span class="st" :style="statusStyle(row.status)">
              {{ statusGlyph(row.status) }} {{ row.status || 'Draft' }}
            </span>
          </template>

          <template #cell-recipients="{ row }">
            <span class="tnum font-semibold">{{ formatNumber(row.recipient_count || 0) }}</span>
          </template>

          <template #cell-delivered="{ row }">
            <span class="tnum">{{ row.delivered != null ? formatNumber(row.delivered) : '—' }}</span>
          </template>

          <template #cell-read="{ row }">
            <span class="tnum">{{ row.read != null ? formatNumber(row.read) : '—' }}</span>
          </template>

          <template #cell-replied="{ row }">
            <span class="tnum" :class="{ 'replied-hot': row.replied > 0 }">
              {{ row.replied != null ? formatNumber(row.replied) : '—' }}
            </span>
          </template>

          <template #cell-outcome="{ row }">
            <span class="tnum font-bold">{{ row.outcome || row.status || '—' }}</span>
          </template>
        </Table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useWhatsApp } from '@/modules/whatsapp/store/whatsapp'
import Icon from '@/shared/icons/Icon.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import ErrorState from '@/shared/ui/ErrorState.vue'
import KpiCard from '@/shared/ui/KpiCard.vue'
import AivoInsight from '@/shared/ui/AivoInsight.vue'
import Table from '@/shared/ui/Table.vue'
import { usePageMeta } from '@/shared/composables/usePageMeta'

usePageMeta({ title: 'WhatsApp', breadcrumb: 'Overview' })

const router = useRouter()
const store = useWhatsApp()

const selectedPeriod = ref(store.dashboardPeriod || 'month')

const summary = computed(() => store.dashboardSummary || {})
const standing = computed(() => store.dashboardAccountStanding || {})
const deliveryHealth = computed(() => store.dashboardDeliveryHealth || {})
const categoryRollup = computed(() => store.dashboardCategoryRollup || [])
const previousPeriod = computed(() => store.dashboardPreviousPeriod || {})
const aivoFacts = computed(() => store.dashboardAivoFacts || { has_issues: false, title: '', summary: '' })
const recentBroadcasts = computed(() => store.recentBroadcasts || [])

const periodSubText = computed(() => {
  if (selectedPeriod.value === '7d') return 'last 7 days'
  if (selectedPeriod.value === 'qtr') return 'this quarter'
  return 'this month'
})

/**
 * Messages by purpose configuration mapped from backend category rollup.
 */
const categoryPurposes = computed(() => {
  const cats = categoryRollup.value || []
  const map = {
    Marketing: {
      name: 'Marketing',
      desc: 'Promotions, newsletters & re-engagement',
      icon: 'send',
      color: '#8B5CF6',
      barColor: 'var(--brand)',
    },
    Utility: {
      name: 'Utility',
      desc: 'Order confirmations & status alerts',
      icon: 'check-circle',
      color: '#06B6D4',
      barColor: 'var(--accent-teal, #14B8A6)',
    },
    Authentication: {
      name: 'Authentication',
      desc: 'One-time passwords & security verification',
      icon: 'shield',
      color: '#F59E0B',
      barColor: 'var(--warning, #F59E0B)',
    },
  }

  const totalVol = cats.reduce((acc, c) => acc + (Number(c.sent) || 0), 0)

  return cats.map((c) => {
    const meta = map[c.category] || {
      name: c.category,
      desc: 'Messaging traffic',
      icon: 'message-circle',
      color: '#64748B',
      barColor: '#64748B',
    }
    const vol = Number(c.sent) || 0
    const pct = totalVol > 0 ? Math.round((vol / totalVol) * 100) : 0
    const readR = c.read_rate != null ? Number(c.read_rate) : null

    return {
      key: c.category,
      name: meta.name,
      desc: meta.desc,
      icon: meta.icon,
      color: meta.color,
      barColor: meta.barColor,
      volume: vol,
      pct,
      metric: readR != null ? `${readR}%` : '—',
      metricSub: 'read rate',
      warn: readR != null && readR < 50 && vol > 0,
    }
  })
})

/**
 * Horizontal Funnel bars for Delivery Health.
 */
const deliveryFunnel = computed(() => {
  const sent = Number(deliveryHealth.value.sent ?? summary.value.sent) || 0
  const deliv = Number(deliveryHealth.value.delivered ?? summary.value.delivered) || 0
  const read = Number(deliveryHealth.value.read ?? summary.value.read) || 0

  const delivPct = deliveryHealth.value.delivered_pct != null
    ? Math.round(Number(deliveryHealth.value.delivered_pct))
    : (sent > 0 ? Math.round((deliv / sent) * 100) : null)
  const readPct = deliveryHealth.value.read_pct != null
    ? Math.round(Number(deliveryHealth.value.read_pct))
    : (sent > 0 ? Math.round((read / sent) * 100) : null)

  return [
    { name: 'Sent', count: sent, pct: sent > 0 ? 100 : null, color: 'var(--brand)', dark: true },
    { name: 'Delivered', count: deliv, pct: delivPct, color: 'var(--accent-teal, #14B8A6)', dark: true },
    { name: 'Read', count: read, pct: readPct, color: '#38BDF8', dark: false },
  ]
})

/**
 * Template approval status dots in Account standing.
 */
const standingTemplates = computed(() => {
  if (standing.value.templates && standing.value.templates.length) {
    return standing.value.templates
  }
  return [
    { label: 'Approved', n: summary.value.templatesApproved || 0, dot: 'var(--success, #10B981)' },
    { label: 'Pending', n: summary.value.templatesPending || 0, dot: 'var(--warning, #F59E0B)' },
    { label: 'Rejected', n: summary.value.templatesRejected || 0, dot: 'var(--danger, #EF4444)' },
  ]
})

const qualityPillClass = computed(() => {
  const q = (summary.value.quality || '').toLowerCase()
  if (q.includes('high') || q.includes('green')) return 'pill-success'
  if (q.includes('medium') || q.includes('yellow')) return 'pill-warn'
  if (q.includes('low') || q.includes('red')) return 'pill-danger'
  return 'pill-neutral'
})

const qualityDeltaTone = computed(() => {
  const q = (summary.value.quality || '').toLowerCase()
  if (q.includes('high') || q.includes('green')) return 'up'
  if (q.includes('medium') || q.includes('yellow')) return 'neutral'
  if (q.includes('low') || q.includes('red')) return 'down'
  return ''
})

const readDelta = computed(() => {
  const curr = summary.value.readPct
  const prev = previousPeriod.value?.read_rate
  return computeDelta(curr, prev)
})

const replyDelta = computed(() => {
  const curr = summary.value.replyPct
  const prev = previousPeriod.value?.reply_rate
  return computeDelta(curr, prev)
})

/**
 * Table columns for recent broadcasts.
 */
const broadcastColumns = [
  { key: 'title', label: 'Broadcast', width: '28%' },
  { key: 'purpose', label: 'Purpose', width: '12%' },
  { key: 'status', label: 'Status', width: '12%' },
  { key: 'recipients', label: 'Recipients', align: 'right', width: '12%' },
  { key: 'delivered', label: 'Delivered', align: 'right', width: '12%' },
  { key: 'read', label: 'Read', align: 'right', width: '12%' },
  { key: 'replied', label: 'Replied', align: 'right', width: '10%' },
  { key: 'outcome', label: 'Outcome', align: 'right', width: '12%' },
]

/**
 * Format numbers with compact comma grouping.
 * @param {number|string} v - Raw value
 * @returns {string} Formatted number
 */
function formatNumber(v) {
  if (v == null || v === '') return '0'
  return Number(v).toLocaleString()
}

/**
 * Compute delta percentage point vs previous period.
 * Returns null if either current or previous period rate is null.
 * @param {number|null} curr - Current percentage
 * @param {number|null} prev - Previous period percentage
 * @returns {{text: string, tone: string}|null}
 */
function computeDelta(curr, prev) {
  if (curr == null || prev == null) return null
  const diff = Math.round(Number(curr) - Number(prev))
  if (diff > 0) return { text: `▲ ${diff}pp vs previous period`, tone: 'up' }
  if (diff < 0) return { text: `▼ ${Math.abs(diff)}pp vs previous period`, tone: 'down' }
  return { text: '0pp vs previous period', tone: 'neutral' }
}

function statusStyle(s) {
  if (s === 'Completed' || s === 'Sent') {
    return 'background: var(--status-success-bg, #DCFCE7); color: var(--status-success-text, #166534);'
  }
  if (s === 'Queued' || s === 'In Progress' || s === 'Scheduled') {
    return 'background: var(--status-info-bg, #E0F2FE); color: var(--status-info-text, #0369A1);'
  }
  if (s === 'Partially Failed' || s === 'Failed') {
    return 'background: var(--status-danger-bg, #FEE2E2); color: var(--status-danger-text, #991B1B);'
  }
  return 'background: var(--status-neutral-bg, #F1F5F9); color: var(--status-neutral-text, #475569);'
}

function statusGlyph(s) {
  if (s === 'Completed' || s === 'Sent') return '●'
  if (s === 'Scheduled') return '◷'
  if (s === 'Queued' || s === 'In Progress') return '◔'
  return '○'
}

function setPeriod(p) {
  selectedPeriod.value = p
  store.fetchDashboardMetrics(p)
}

function openNewBroadcast() {
  router.push({ name: 'WhatsAppBroadcastWizard' })
}

function openBroadcast(row) {
  router.push({ name: 'WhatsAppBulkMessages', query: { search: row.title || row.name } })
}

onMounted(() => {
  store.fetchDashboardMetrics(selectedPeriod.value)
})
</script>

<style scoped>
.dash {
  display: flex;
  flex-direction: column;
  gap: 18px;
  width: 100%;
  padding: 0 0 var(--page-gutter);
}
.tnum { font-variant-numeric: tabular-nums; }

/* ── Header ───────────────────────────────────────────────────── */
.phead {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.phead-title {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.01em;
  color: var(--text-primary);
  margin: 0;
}
.phead-sub {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
}
.phead-sub b {
  color: var(--text-primary);
  font-weight: 700;
}
.phead-r {
  display: flex;
  align-items: center;
  gap: 12px;
}

.l-segment {
  display: inline-flex;
  background: var(--bg-sunken, #F1F5F9);
  border: 1px solid var(--border-soft, #E2E8F0);
  border-radius: var(--radius-md, 8px);
  padding: 3px;
  gap: 2px;
}
.seg-btn {
  height: 30px;
  padding: 0 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.seg-btn:hover {
  color: var(--text-primary);
}
.seg-btn.is-active {
  background: var(--bg-surface, #FFFFFF);
  color: var(--brand);
  box-shadow: var(--shadow-sm);
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 16px;
  border: none;
  border-radius: var(--radius-md, 8px);
  background: var(--brand);
  color: #ffffff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s ease;
}
.btn-primary:hover {
  opacity: 0.92;
}

/* ── KPI Grid ─────────────────────────────────────────────────── */
.l-metrics {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}

/* ── Grids ────────────────────────────────────────────────────── */
.grid-hero {
  display: grid;
  grid-template-columns: 1.55fr 1fr;
  gap: 16px;
}
.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.panel {
  background: var(--bg-surface);
  border: 1px solid var(--border-soft);
  box-shadow: var(--shadow-sm);
  border-radius: var(--radius-lg, 12px);
  overflow: hidden;
}
.card-h {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 13px 20px;
  border-bottom: 1px solid var(--border-soft);
}
.card-h h3 {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.card-h .sub {
  font-size: 11.5px;
  color: var(--text-tertiary);
  font-weight: 500;
}
.view-all-link {
  background: none;
  border: none;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--brand);
  cursor: pointer;
  padding: 0;
}
.view-all-link:hover { text-decoration: underline; }

/* ── Messages by purpose ──────────────────────────────────────── */
.pur {
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-soft);
}
.pur:last-child {
  border-bottom: none;
}
.pur-row {
  display: grid;
  grid-template-columns: 40px 1fr auto auto;
  align-items: center;
  gap: 14px;
}
.pur-ic {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  color: #ffffff;
}
.pur-meta {
  min-width: 0;
}
.pur-name {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-primary);
}
.pur-desc {
  font-size: 11.5px;
  color: var(--text-tertiary);
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pur-vol {
  text-align: right;
  padding-right: 6px;
}
.pur-vol .pv {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
.pur-vol .pl {
  font-size: var(--fs-2xs);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 700;
}
.pur-out {
  text-align: right;
  min-width: 96px;
}
.pur-out .po {
  font-size: 15px;
  font-weight: 800;
}
.pur-out .pos {
  font-size: var(--fs-2xs);
  color: var(--text-tertiary);
  font-weight: 600;
  margin-top: 1px;
}
.pur-bar {
  height: 4px;
  border-radius: 999px;
  background: var(--bg-sunken);
  overflow: hidden;
  margin-top: 11px;
}
.pur-bar i {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width 0.3s ease;
}

/* ── Delivery health funnel ───────────────────────────────────── */
.dfun {
  padding: 16px 20px 10px;
}
.dfun-row {
  display: grid;
  grid-template-columns: 78px 1fr 92px;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.dfun-row .dl {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}
.dfun-track {
  height: 22px;
  background: var(--bg-sunken);
  border-radius: var(--radius-sm, 6px);
  overflow: hidden;
}
.dfun-fill {
  height: 100%;
  border-radius: var(--radius-sm, 6px);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 9px;
  font-size: 11px;
  font-weight: 800;
  transition: width 0.3s ease;
}
.dfun-pct {
  text-align: right;
  font-size: 13px;
  font-weight: 800;
  color: var(--text-primary);
}
.dfun-pct small {
  display: block;
  font-size: var(--fs-2xs);
  color: var(--text-tertiary);
  font-weight: 600;
}
.dfun-foot {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-top: 1px solid var(--border-soft);
  background: var(--brand-lighter, rgba(37, 99, 235, 0.05));
  border-radius: 0 0 var(--radius-lg, 12px) var(--radius-lg, 12px);
}
.dfun-foot .big {
  font-size: 24px;
  font-weight: 800;
  color: var(--brand);
  letter-spacing: -0.02em;
}
.dfun-foot .fl {
  font-size: 11.5px;
  color: var(--text-secondary);
  line-height: 1.45;
}
.dfun-foot .fl b {
  color: var(--text-primary);
}

/* ── Account standing ─────────────────────────────────────────── */
.health {
  padding: 8px 20px 16px;
}
.h-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-soft);
}
.h-row:last-child {
  border-bottom: none;
}
.h-row.hcol {
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}
.h-k {
  font-size: 12.5px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
}
.h-k .gi {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: var(--brand-lighter, rgba(37, 99, 235, 0.08));
  display: grid;
  place-items: center;
  color: var(--text-secondary);
}
.h-v {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}
.tier-unit {
  color: var(--text-tertiary);
  font-weight: 600;
  font-size: 11.5px;
}
.pill {
  font-size: 11px;
  font-weight: 800;
  padding: 2px 10px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.pill-success {
  background: var(--status-success-bg, #DCFCE7);
  color: var(--status-success-text, #166534);
}
.pill-warn {
  background: var(--status-warning-bg, #FEF3C7);
  color: var(--status-warning-text, #92400E);
}
.pill-danger {
  background: var(--status-danger-bg, #FEE2E2);
  color: var(--status-danger-text, #991B1B);
}
.pill-neutral {
  background: var(--status-neutral-bg, #F1F5F9);
  color: var(--status-neutral-text, #475569);
}
.tmpls {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  width: 100%;
  padding-left: 2px;
}
.tmpl {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--text-secondary);
}
.tmpl .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.tmpl .num {
  font-weight: 800;
  color: var(--text-primary);
}

/* ── Aivo Diagnostics Card ────────────────────────────────────── */
.aicard {
  background: var(--ai-bg, #0b111e);
  border: 1px solid var(--ai-border, #1e293b);
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.aicard-h {
  padding: 16px 20px 14px;
  border-bottom: 1px solid var(--ai-border, #1e293b);
}
.aicard-k {
  font-size: var(--fs-2xs);
  font-weight: 800;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--ai-label, #38bdf8);
  display: flex;
  align-items: center;
  gap: 7px;
}
.aicard-t {
  font-size: 16px;
  font-weight: 800;
  color: #ffffff;
  letter-spacing: -0.015em;
  margin-top: 7px;
}
.aicard-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  padding: 16px 20px;
}
.issue {
  background: var(--ai-inset, rgba(15, 23, 42, 0.7));
  border: 1px solid var(--ai-border, #1e293b);
  border-radius: var(--radius-md, 8px);
  padding: 15px 16px;
  display: flex;
  flex-direction: column;
}
.dchip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-2xs);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 3px 10px;
  border-radius: 999px;
  align-self: flex-start;
}
.dchip.warn {
  background: rgba(245, 158, 11, 0.16);
  color: #FBBF4E;
  border: 1px solid rgba(245, 158, 11, 0.32);
}
.dchip.danger {
  background: rgba(239, 68, 68, 0.15);
  color: #F98A82;
  border: 1px solid rgba(239, 68, 68, 0.3);
}
.issue-when {
  font-size: 11px;
  color: var(--ai-muted, #94a3b8);
  font-weight: 600;
  margin-top: 8px;
}
.issue-t {
  font-size: 14px;
  font-weight: 800;
  color: #ffffff;
  letter-spacing: -0.01em;
  margin: 7px 0 6px;
  line-height: 1.3;
}
.issue-why {
  font-size: 12.5px;
  color: var(--ai-text, #e2e8f0);
  line-height: 1.55;
}
.issue-why :deep(b) {
  color: #ffffff;
  font-weight: 700;
}
.rej {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--ai-border, #1e293b);
  border-radius: 8px;
  overflow: hidden;
  margin: 12px 0 2px;
}
.rej-row {
  background: var(--ai-bg, #0b111e);
  padding: 9px 11px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.rej-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rej-name {
  font-size: 12.5px;
  font-weight: 700;
  color: #ffffff;
}
.rej-reason {
  font-size: var(--fs-2xs);
  font-weight: 700;
  color: #F98A82;
  background: rgba(239, 68, 68, 0.13);
  padding: 1px 7px;
  border-radius: 999px;
  margin-left: auto;
  white-space: nowrap;
}
.rej-fix {
  font-size: 11.5px;
  color: var(--ai-text, #e2e8f0);
  display: flex;
  gap: 7px;
}
.rej-fix::before {
  content: "→";
  color: var(--ai-label, #38bdf8);
  font-weight: 800;
  flex-shrink: 0;
}
.fix-h {
  font-size: var(--fs-2xs);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ai-label, #38bdf8);
  margin: 14px 0 8px;
}
.fix {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin: 0;
  padding: 0;
}
.fix li {
  font-size: 12.5px;
  color: var(--ai-text, #e2e8f0);
  line-height: 1.45;
  display: flex;
  gap: 9px;
}
.fix li::before {
  content: "→";
  color: var(--ai-label, #38bdf8);
  font-weight: 800;
  flex-shrink: 0;
}
.aicard-src {
  font-size: 11px;
  color: var(--ai-muted, #94a3b8);
  padding: 12px 20px;
  border-top: 1px solid var(--ai-border, #1e293b);
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── Broadcasts Table & Cells ─────────────────────────────────── */
.nm-wrap {
  cursor: pointer;
}
.nm-wrap:hover .nm {
  color: var(--brand);
  text-decoration: underline;
}
.nm {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.co {
  font-size: 11.5px;
  color: var(--text-tertiary);
  margin-top: 2px;
}
.tag {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--bg-sunken);
  color: var(--text-secondary);
}
.st {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  font-weight: 700;
  padding: 2px 9px;
  border-radius: 999px;
  white-space: nowrap;
}
.replied-hot {
  color: var(--success, #10B981);
  font-weight: 700;
}

.btn-ai-action {
  font-size: 12px;
  font-weight: 600;
  padding: 7px 14px;
  border-radius: var(--radius-pill, 999px);
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #ffffff;
  cursor: pointer;
  transition: all 0.15s ease;
}
.btn-ai-action:hover {
  background: rgba(255, 255, 255, 0.2);
}

.wdash-error {
  padding: 12px 16px;
  border-radius: var(--radius-md, 8px);
  background: var(--status-danger-bg, #FEE2E2);
  color: var(--status-danger-text, #991B1B);
  font-size: 13px;
  font-weight: 500;
}

.wdash-loading {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}
.skeleton-kpi {
  height: 96px;
  background: var(--bg-sunken);
  border-radius: var(--radius-md, 8px);
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@media (max-width: 1080px) {
  .l-metrics { grid-template-columns: repeat(3, 1fr); }
  .grid-hero, .grid-2, .aicard-body { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .l-metrics { grid-template-columns: repeat(2, 1fr); }
  .dash { padding: 16px 14px 60px; }
}
</style>
