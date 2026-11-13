<!--
  MarketingMessagesPanel — account-level WhatsApp Marketing Messages metrics.

  Shows the period totals (sent, delivered, read, clicked), rates, cost per
  currency, conversions and a per-template table. Fetches
  `get_marketing_metrics_summary` and `get_marketing_metrics_by_template`
  and reloads when `account`, `days` or `reloadToken` change.

  Honesty rules: a value Meta did not report is "n/a", never 0; money is
  shown per currency (never summed); conversions need Meta Pixel / CAPI.

  Props:
    account     — WhatsApp Account name ('' = server default / all)
    days        — look-back window in days (server clamps it)
    reloadToken — bump to force a reload (e.g. the page's Refresh button)
-->
<template>
  <section class="mm-panel" aria-label="Marketing Messages metrics">
    <header class="mm-head">
      <h3 class="mm-title">Marketing Messages</h3>
      <span v-if="summary?.period" class="mm-period">
        {{ summary.period.start }} to {{ summary.period.end }}
      </span>
    </header>

    <Shimmer v-if="loading" variant="kpis" :count="4" />

    <ErrorState v-else-if="error" title="Could not load Marketing Messages metrics" :message="error" :retry="load">
      <button type="button" class="mm-btn" @click="load">Retry</button>
    </ErrorState>

    <EmptyState
      v-else-if="!summary?.has_data"
      title="No Marketing Messages data yet"
      description="Metrics appear after Meta reports sends for this account."
    />

    <template v-else>
      <div class="mm-kpis">
        <KpiCard label="Sent" :value="formatCount(summary.totals.sent)" />
        <KpiCard label="Delivered" :value="formatCount(summary.totals.delivered)"
                 :sub="`Delivery rate ${formatRate(summary.rates.delivery_rate)}`" />
        <KpiCard label="Read" :value="formatCount(summary.totals.read)"
                 :sub="`Read rate ${formatRate(summary.rates.read_rate)}`" />
        <KpiCard label="Clicked" :value="formatCount(summary.totals.clicked)"
                 :sub="summary.clicks_supported
                   ? `Click rate ${formatRate(summary.rates.click_rate)}`
                   : 'Clicks are not reported for this account'" />
      </div>

      <ul v-if="summary.cost.length" class="mm-cost" aria-label="Cost by currency">
        <li v-for="c in summary.cost" :key="c.currency || 'none'">
          Spent {{ formatMoney(c.amount_spent, c.currency) }}
          <span class="mm-muted">
            · per delivered {{ formatMoney(c.cost_per_delivered, c.currency) }}
            · per click {{ formatMoney(c.cost_per_click, c.currency) }}
          </span>
        </li>
      </ul>

      <p class="mm-conv">
        <span class="mm-label">Conversions</span>
        <template v-if="summary.conversions_available && conversionText.length">
          <span v-for="line in conversionText" :key="line" class="mm-chip">{{ line }}</span>
        </template>
        <span v-else-if="summary.conversions_available" class="mm-muted">{{ NO_CONVERSIONS_HINT }}</span>
        <span v-else class="mm-muted">{{ CONVERSIONS_HINT }}</span>
      </p>

      <div class="mm-table" role="region" aria-label="Marketing Messages by template" tabindex="0">
        <Table :columns="COLUMNS" :rows="templates" row-key="template_id"
               :empty="{ title: 'No template data' }">
          <template #cell-template="{ row }">
            <span class="mm-name" :title="templateName(row)">{{ templateName(row) }}</span>
          </template>
          <template #cell-sent="{ row }">{{ formatCount(row.sent) }}</template>
          <template #cell-delivered="{ row }">{{ formatCount(row.delivered) }}</template>
          <template #cell-read="{ row }">{{ formatCount(row.read) }}</template>
          <template #cell-clicked="{ row }">{{ formatCount(row.clicked) }}</template>
          <template #cell-read_rate="{ row }">{{ formatRate(row.read_rate) }}</template>
        </Table>
      </div>
      <p v-if="truncated" class="mm-muted mm-note">
        Showing the top templates by sends; more exist.
      </p>
    </template>
  </section>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { callRpc } from '@/services/_factory'
import KpiCard from '@/shared/ui/KpiCard.vue'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorState from '@/shared/ui/ErrorState.vue'
import Shimmer from '@/shared/ui/Shimmer.vue'
import Table from '@/shared/ui/Table.vue'
import {
  CONVERSIONS_HINT, NO_CONVERSIONS_HINT, formatCount, formatRate, formatMoney, conversionLines,
} from './metricsFormat.js'

const props = defineProps({
  account: { type: String, default: '' },
  days: { type: Number, default: null },
  reloadToken: { type: Number, default: 0 },
})

const SUMMARY_METHOD = 'msuite_whatsapp.api.v1.app.analytics_query.get_marketing_metrics_summary'
const TEMPLATE_METHOD = 'msuite_whatsapp.api.v1.app.analytics_query.get_marketing_metrics_by_template'
const COLUMNS = [
  { key: 'template', label: 'Template' },
  { key: 'sent', label: 'Sent', align: 'right' },
  { key: 'delivered', label: 'Delivered', align: 'right' },
  { key: 'read', label: 'Read', align: 'right' },
  { key: 'clicked', label: 'Clicked', align: 'right' },
  { key: 'read_rate', label: 'Read rate', align: 'right' },
]

const loading = ref(true)
const error = ref('')
const summary = ref(null)
const templates = ref([])
const truncated = ref(false)
let requestId = 0

const conversionText = computed(() => conversionLines(summary.value?.conversions))

/** @param {{template?: string|null, template_id: string}} row @returns {string} */
function templateName(row) {
  return row.template || row.template_id
}

/**
 * Load summary + per-template metrics. Ignores out-of-order responses.
 * Side effects: two read-only RPC calls; sets loading/error/data state.
 * @returns {Promise<void>}
 */
async function load() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  const params = {}
  if (props.account) params.account_name = props.account
  if (props.days) params.days = props.days
  try {
    const [sum, byTemplate] = await Promise.all([
      callRpc(SUMMARY_METHOD, params, 'MarketingSummary'),
      callRpc(TEMPLATE_METHOD, params, 'MarketingByTemplate'),
    ])
    if (id !== requestId) return
    summary.value = sum
    templates.value = byTemplate?.templates || []
    truncated.value = !!byTemplate?.truncated
  } catch (e) {
    if (id !== requestId) return
    error.value = e?.messages?.[0] || e?.message || 'Please try again.'
  } finally {
    if (id === requestId) loading.value = false
  }
}

watch(() => [props.account, props.days, props.reloadToken], load)
onMounted(load)
defineExpose({ load })
</script>

<style scoped>
.mm-panel { background: var(--bg-surface); border: 1px solid var(--border-soft); border-radius: var(--radius-lg); padding: 16px; margin-top: 16px; }
.mm-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; justify-content: space-between; margin-bottom: 12px; }
.mm-title { font-size: 15px; font-weight: 600; margin: 0; }
.mm-period, .mm-muted { font-size: 12px; color: var(--text-tertiary); }
.mm-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.mm-cost { list-style: none; padding: 0; margin: 12px 0 0; font-size: 13px; }
.mm-conv { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 12px 0; font-size: 13px; }
.mm-label { font-weight: 600; margin-right: 4px; }
.mm-chip { background: var(--bg-sunken); border-radius: 999px; padding: 2px 10px; font-size: 12px; }
.mm-table { overflow-x: auto; }
.mm-table:focus-visible, .mm-btn:focus-visible { outline: 2px solid var(--brand, currentColor); outline-offset: 2px; }
.mm-name { display: inline-block; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
.mm-note { margin: 8px 0 0; }
.mm-btn { padding: 6px 14px; border: 1px solid var(--border-soft); border-radius: var(--radius-md); background: var(--bg-surface); cursor: pointer; }
@media (max-width: 768px) { .mm-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 480px) { .mm-kpis { grid-template-columns: 1fr; } }
</style>
