<!-- Shimmer — the ONE loading placeholder for lists, cards, tables, KPI rows and charts.
     Known layouts shimmer in place (the frame and labels paint at once; only the unknowns
     are skeletons) so nothing jumps when data lands. System waits with no known layout
     use <LLoader />; AI work uses <AivoAvatar thinking />. Never mix them up.

       <Shimmer variant="rows" :count="6" />      list rows (avatar + two lines + chip)
       <Shimmer variant="cards" :count="6" />     responsive card grid
       <Shimmer variant="kpis" :count="5" />      KPI strip
       <Shimmer variant="table" :count="6" :cols="5" />
       <Shimmer variant="chart" />                chart panel (bars)
       <Shimmer variant="lines" :count="3" />     paragraph
     Tokens only — follows light/dark and any tenant theme. -->
<template>
  <div class="shm" :class="`shm--${variant}`" role="status" aria-busy="true" :aria-label="label">
    <!-- rows -->
    <template v-if="variant === 'rows'">
      <div v-for="i in count" :key="i" class="shm-row">
        <span v-if="avatar" class="sk shm-avatar" />
        <span class="shm-col">
          <span class="sk sk-line" :style="{ width: widths[i % widths.length] }" />
          <span class="sk sk-line sk-line--sm" :style="{ width: widths[(i + 2) % widths.length] }" />
        </span>
        <span class="sk shm-chip" />
      </div>
    </template>

    <!-- cards -->
    <template v-else-if="variant === 'cards'">
      <div v-for="i in count" :key="i" class="shm-card">
        <span class="sk shm-card__media" />
        <span class="sk sk-line" :style="{ width: widths[i % widths.length] }" />
        <span class="sk sk-line sk-line--sm" style="width: 85%" />
        <span class="shm-card__foot"><span class="sk shm-chip" /><span class="sk shm-chip shm-chip--sm" /></span>
      </div>
    </template>

    <!-- kpis -->
    <template v-else-if="variant === 'kpis'">
      <div v-for="i in count" :key="i" class="shm-kpi">
        <span class="sk sk-line sk-line--sm" style="width: 55%" />
        <span class="sk sk-line sk-line--xl" style="width: 40%" />
        <span class="sk sk-line sk-line--sm" style="width: 70%" />
      </div>
    </template>

    <!-- table -->
    <template v-else-if="variant === 'table'">
      <div class="shm-thead"><span v-for="c in cols" :key="c" class="sk sk-line sk-line--sm" :style="{ width: c === 1 ? '40%' : '55%' }" /></div>
      <div v-for="i in count" :key="i" class="shm-tr" :style="{ gridTemplateColumns: `2fr repeat(${cols - 1}, 1fr)` }">
        <span v-for="c in cols" :key="c" class="sk sk-line" :style="{ width: cellWidth(i, c) }" />
      </div>
    </template>

    <!-- chart -->
    <template v-else-if="variant === 'chart'">
      <div class="shm-chart">
        <span v-for="(h, i) in bars" :key="i" class="sk shm-bar" :style="{ height: h + '%' }" />
      </div>
    </template>

    <!-- lines (default) -->
    <template v-else>
      <span v-for="i in count" :key="i" class="sk sk-line" :style="{ width: i === count ? '60%' : '100%' }" />
    </template>
    <span class="shm-sr">{{ label }}</span>
  </div>
</template>

<script setup>
defineProps({
  variant: { type: String, default: 'rows' }, // rows | cards | kpis | table | chart | lines
  count: { type: Number, default: 5 },
  cols: { type: Number, default: 5 }, // table only
  avatar: { type: Boolean, default: true }, // rows only
  label: { type: String, default: 'Loading' },
})
const widths = ['62%', '78%', '54%', '70%', '88%']
const bars = [38, 62, 48, 80, 56, 70, 44, 90, 60, 52]
const cellWidth = (r, c) => (c === 1 ? ['72%', '58%', '84%', '66%'][r % 4] : ['60%', '45%', '70%', '52%'][(r + c) % 4])
</script>

<style scoped>
.shm { width: 100%; box-sizing: border-box; }
.shm-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

.shm--rows { display: flex; flex-direction: column; }
.shm-row { display: flex; align-items: center; gap: 12px; padding: 13px 16px; border-bottom: 1px solid var(--border-soft); }
.shm-row:last-child { border-bottom: none; }
.shm-avatar { width: 34px; height: 34px; border-radius: 50%; flex: none; }
.shm-col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.shm-chip { width: 64px; height: 22px; border-radius: var(--radius-pill); flex: none; }
.shm-chip--sm { width: 40px; }

.shm--cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.shm-card { background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); padding: 14px; display: flex; flex-direction: column; gap: 10px; }
.shm-card__media { height: 110px; border-radius: var(--radius-md); }
.shm-card__foot { display: flex; gap: 8px; margin-top: 4px; }

.shm--kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.shm-kpi { background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); padding: 16px 18px; display: flex; flex-direction: column; gap: 10px; }

.shm--table { background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
.shm-thead { display: flex; gap: 24px; padding: 12px 16px; background: var(--bg-sunken); border-bottom: 1px solid var(--border); }
.shm-thead .sk { flex: 1; }
.shm-tr { display: grid; gap: 24px; align-items: center; padding: 14px 16px; border-bottom: 1px solid var(--border-soft); }
.shm-tr:last-child { border-bottom: none; }

.shm--chart { background: transparent; }
.shm-chart { height: 100%; min-height: 180px; display: flex; align-items: flex-end; gap: 10px; padding: 16px 12px 8px; }
.shm-bar { flex: 1; border-radius: 6px 6px 2px 2px; }

.shm--lines { display: flex; flex-direction: column; gap: 10px; }
</style>
