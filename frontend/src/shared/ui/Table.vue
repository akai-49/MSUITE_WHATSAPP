<!--
  Generic data table. Columns are declarative; rows render through a
  per-cell slot so callers keep full control of formatting (StatusPill,
  links, etc.) without writing table chrome (header, alignment, empty
  state, horizontal scroll) themselves every time — see
  FRONTEND_ARCHITECTURE_AUDIT.md §8/§12 ("Table primitives reinvented
  per module").

  Deliberately minimal: no built-in sort/pagination — callers own that
  via the `columns`/`rows` they pass in (CRM Leads/Deals lists already
  paginate server-side through their store). Wrapping in `.tbl-scroll`
  gives every consumer horizontal-scroll-on-overflow for free instead
  of each page reinventing it.

  Props:
    columns — [{ key, label, width?, align? }]
    rows    — array of row objects
    rowKey  — field name used as :key (default 'name')
    loading — shows a lightweight skeleton instead of rows
    empty   — { title, description } passed to <EmptyState> when rows is empty

  Slots:
    cell-<key>   — per-column cell renderer, scope: { row, value }
    header-<key> — optional header-cell renderer (e.g. a select-all
                   checkbox); falls back to the column label
    empty-actions — forwarded to EmptyState's `actions` slot
-->
<template>
  <div class="tbl-scroll">
    <table class="tbl">
      <thead>
        <tr>
          <th
            v-for="col in columns"
            :key="col.key"
            :style="{ width: col.width, textAlign: col.align || 'left' }"
          >
            <slot :name="`header-${col.key}`">{{ col.label }}</slot>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="loading" class="tbl-skel-row">
          <td :colspan="columns.length">
            <Shimmer variant="rows" :count="5" :avatar="false" />
          </td>
        </tr>
        <tr v-for="row in rows" v-else :key="row[rowKey] ?? row.name">
          <td
            v-for="col in columns"
            :key="col.key"
            :style="{ textAlign: col.align || 'left' }"
          >
            <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
              {{ row[col.key] }}
            </slot>
          </td>
        </tr>
      </tbody>
    </table>

    <EmptyState
      v-if="!loading && !rows.length"
      :title="empty.title || 'Nothing here yet'"
      :description="empty.description || ''"
    >
      <template v-if="$slots['empty-actions']" #actions>
        <slot name="empty-actions" />
      </template>
    </EmptyState>
  </div>
</template>

<script setup>
import EmptyState from '@/shared/ui/EmptyState.vue'
import Skeleton from '@/shared/ui/Skeleton.vue'

defineProps({
  columns: { type: Array,   required: true },
  rows:    { type: Array,   default: () => [] },
  rowKey:  { type: String,  default: 'name' },
  loading: { type: Boolean, default: false },
  empty:   { type: Object,  default: () => ({}) },
})
</script>

<style scoped>
/* Horizontal scroll on overflow instead of clipping/wrapping —
   audit §"TABLE RENDERING": no clipped text, no broken wrapping. */
.tbl-scroll {
  width: 100%;
  overflow-x: auto;
}
.tbl {
  width: 100%;
  min-width: max-content;
  border-collapse: collapse;
  font-size: 13.5px;
  color: var(--ink-900, var(--ink-900));
}
.tbl thead th {
  position: sticky;
  top: 0;
  background: var(--ink-25, var(--ink-25));
  border-bottom: 1.5px solid var(--ink-100, var(--ink-100));
  padding: 10px 14px;
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--ink-500, var(--ink-500));
  white-space: nowrap;
}
.tbl tbody td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--ink-50, var(--ink-50));
  vertical-align: middle;
}
.tbl tbody tr:hover {
  background: var(--ink-25, var(--ink-25));
}

.tbl-skel-row td { padding: 16px 14px; }
</style>
