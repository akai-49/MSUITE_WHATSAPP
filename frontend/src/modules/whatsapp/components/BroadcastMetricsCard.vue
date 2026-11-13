<!--
  BroadcastMetricsCard — delivery and engagement for one WhatsApp broadcast
  (`broadcast`) or a whole Marketing Campaign (`campaign`).

  Sent / Delivered / Read / Failed are exact (counted from our own message
  rows). Clicks and conversions come from Meta per template per day, so each
  carries an attribution badge: Exact, Template-level (all sends of the
  template, with its date range) or Not available. A missing value is
  "n/a", never 0.

  Props:
    broadcast — Bulk WhatsApp Message name (one of broadcast/campaign)
    campaign  — Marketing Campaign name; shows the summed totals + a
                per-broadcast table instead of the template-level block
-->
<template>
  <section class="bm-card" aria-label="Broadcast metrics">
    <Shimmer v-if="loading" variant="kpis" :count="4" />

    <ErrorState v-else-if="error" title="Could not load metrics" :message="error" :retry="load">
      <button type="button" class="bm-btn" @click="load">Retry</button>
    </ErrorState>

    <EmptyState v-else-if="isEmpty" title="No sends yet"
                description="Metrics appear once messages are sent." />

    <template v-else-if="data">
      <div class="bm-kpis">
        <KpiCard label="Sent" :value="formatCount(data.totals.sent)" />
        <KpiCard label="Delivered" :value="formatCount(data.totals.delivered)"
                 :sub="`Delivery rate ${formatRate(data.rates.delivery)}`" />
        <KpiCard label="Read" :value="formatCount(data.totals.read)"
                 :sub="`Read rate ${formatRate(data.rates.read)}`" />
        <KpiCard label="Failed" :value="formatCount(data.totals.failed)" />
      </div>

      <div v-if="routes.length" class="bm-routes" aria-label="Send route">
        <span class="bm-label">Route</span>
        <span v-for="r in routes" :key="r.key" class="bm-chip">{{ r.label }} {{ formatCount(r.count) }}</span>
      </div>

      <dl class="bm-engage">
        <div v-for="row in engagement" :key="row.key" class="bm-row">
          <dt>{{ row.label }} <AttributionBadge :level="row.level" :reason="row.reason" /></dt>
          <dd>
            <span v-for="line in row.lines" :key="line" class="bm-line">{{ line }}</span>
          </dd>
        </div>
      </dl>

      <p v-if="data.template_level && usesTemplateLevel" class="bm-caption">
        {{ data.template_level.caption }}, {{ data.template_level.from_date }} to {{ data.template_level.to_date }}
        <span v-if="data.template_level.complete === false" class="bm-warn" role="alert">
          Incomplete: Meta data is missing for {{ data.template_level.missing_days?.length ?? 0 }} day(s).
        </span>
      </p>
      <p v-else-if="isCampaign && usesTemplateLevel" class="bm-caption">
        Template-level numbers are shared with other sends of the same template.
      </p>

      <div v-if="isCampaign && data.broadcasts?.length" class="bm-table" role="region"
           aria-label="Broadcasts in this campaign" tabindex="0">
        <Table :columns="COLUMNS" :rows="data.broadcasts" row-key="name">
          <template #cell-title="{ row }">
            <span class="bm-name" :title="row.title || row.name">{{ row.title || row.name }}</span>
          </template>
          <template #cell-sent="{ row }">{{ formatCount(row.totals.sent) }}</template>
          <template #cell-delivered="{ row }">{{ formatCount(row.totals.delivered) }}</template>
          <template #cell-read="{ row }">{{ formatCount(row.totals.read) }}</template>
          <template #cell-failed="{ row }">{{ formatCount(row.totals.failed) }}</template>
        </Table>
      </div>
      <p v-if="data.truncated" class="bm-caption">Showing the first broadcasts only; more exist.</p>
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
import AttributionBadge from './AttributionBadge.vue'
import {
  CONVERSIONS_HINT, NOT_AVAILABLE, formatCount, formatRate, breakdownRows, conversionLines,
} from './metricsFormat.js'

const props = defineProps({
  broadcast: { type: String, default: '' },
  campaign: { type: String, default: '' },
})

// Campaign totals are never summed for Meta-reported metrics (shared templates would double count).
const PER_BROADCAST = 'Not summed across broadcasts'
const BROADCAST_METHOD = 'msuite_whatsapp.api.v1.app.bulk_messages.get_broadcast_metrics'
const CAMPAIGN_METHOD = 'msuite_whatsapp.api.v1.app.bulk_messages.get_campaign_metrics'
const COLUMNS = [
  { key: 'title', label: 'Broadcast' },
  { key: 'sent', label: 'Sent', align: 'right' },
  { key: 'delivered', label: 'Delivered', align: 'right' },
  { key: 'read', label: 'Read', align: 'right' },
  { key: 'failed', label: 'Failed', align: 'right' },
]

const loading = ref(true)
const error = ref('')
const data = ref(null)
let requestId = 0

const isCampaign = computed(() => !props.broadcast && !!props.campaign)
const isEmpty = computed(() => {
  const t = data.value?.totals
  return !!data.value && !isCampaign.value && !(t?.sent || t?.queued || t?.failed || t?.recipients)
})
const routes = computed(() => breakdownRows(data.value?.send_path_breakdown))
const usesTemplateLevel = computed(() => {
  const a = data.value?.attribution
  return a?.clicks === 'template_level' || a?.conversions === 'template_level'
})

/**
 * Lines to show for one metric under its attribution level.
 * @param {'clicks'|'conversions'} kind
 * @param {string} key - value key for scalar metrics (clicked / quick_reply_clicked)
 * @returns {string[]}
 */
function linesFor(kind, key) {
  const level = data.value.attribution[kind]
  const source = level === 'exact' ? data.value.attribution.values
    : level === 'template_level' ? data.value.template_level : null
  if (!source && level !== 'unavailable') return [PER_BROADCAST]
  if (!source) return [kind === 'conversions' ? CONVERSIONS_HINT : NOT_AVAILABLE]
  if (kind === 'conversions') {
    const lines = conversionLines(source.conversions)
    return lines.length ? lines : [NOT_AVAILABLE]
  }
  return [formatCount(source[key])]
}

const engagement = computed(() => {
  if (!data.value?.attribution) return []
  const a = data.value.attribution
  return [
    { key: 'clicks', label: 'Clicks', level: a.clicks, reason: a.reason, lines: linesFor('clicks', 'clicked') },
    { key: 'qr', label: 'Quick-reply clicks', level: a.clicks, reason: a.reason, lines: linesFor('clicks', 'quick_reply_clicked') },
    { key: 'conv', label: 'Conversions', level: a.conversions, reason: a.reason, lines: linesFor('conversions') },
  ]
})

/**
 * Load metrics for the broadcast or campaign. Ignores out-of-order responses.
 * Side effects: one read-only RPC call; sets loading/error/data state.
 * @returns {Promise<void>}
 */
async function load() {
  const target = props.broadcast || props.campaign
  if (!target) { loading.value = false; data.value = null; return }
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const res = props.broadcast
      ? await callRpc(BROADCAST_METHOD, { bulk_message: props.broadcast }, 'BroadcastMetrics')
      : await callRpc(CAMPAIGN_METHOD, { campaign: props.campaign }, 'CampaignMetrics')
    if (id !== requestId) return
    data.value = res
  } catch (e) {
    if (id !== requestId) return
    data.value = null
    error.value = e?.messages?.[0] || e?.message || 'Please try again.'
  } finally {
    if (id === requestId) loading.value = false
  }
}

watch(() => [props.broadcast, props.campaign], load)
onMounted(load)
defineExpose({ load })
</script>

<style scoped>
.bm-card { padding: 4px 0; }
.bm-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.bm-routes { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 12px; font-size: 13px; }
.bm-label { font-weight: 600; }
.bm-chip { background: var(--bg-sunken); border-radius: 999px; padding: 2px 10px; font-size: 12px; }
.bm-engage { margin: 12px 0 0; }
.bm-row { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px; padding: 8px 0; border-top: 1px solid var(--border-soft); font-size: 13px; }
.bm-row dt { display: flex; gap: 8px; align-items: center; }
.bm-row dd { margin: 0; display: flex; flex-direction: column; align-items: flex-end; font-variant-numeric: tabular-nums; }
.bm-caption { font-size: 12px; color: var(--text-tertiary); margin: 8px 0 0; }
.bm-warn { color: var(--warning); margin-left: 6px; }
.bm-table { overflow-x: auto; margin-top: 12px; }
.bm-table:focus-visible, .bm-btn:focus-visible { outline: 2px solid var(--brand, currentColor); outline-offset: 2px; }
.bm-name { display: inline-block; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
.bm-btn { padding: 6px 14px; border: 1px solid var(--border-soft); border-radius: var(--radius-md); background: var(--bg-surface); cursor: pointer; }
@media (max-width: 768px) { .bm-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 480px) { .bm-kpis { grid-template-columns: 1fr; } .bm-row dd { align-items: flex-start; } }
</style>
