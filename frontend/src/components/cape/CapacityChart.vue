<template>
  <div class="chart-card">
    <div class="title">Capacity</div>
    <svg :viewBox="`0 0 ${w} ${h}`" class="svg">
      <line :x1="pad" :y1="h-pad" :x2="w-pad" :y2="h-pad" class="axis" />
      <line :x1="pad" :y1="pad" :x2="pad" :y2="h-pad" class="axis" />
      <line :x1="pad" :y1="limitY" :x2="w-pad" :y2="limitY" class="limit" />
      <polyline :points="toPoints(mfg)" class="line mfg" />
      <polyline :points="toPoints(dist)" class="line dist" />
    </svg>
  </div>
</template>

<script setup>
const props = defineProps({ chart: { type: Object, default: () => ({}) } })
const w = 420
const h = 200
const pad = 22
const mfg = (props.chart?.series?.mfg_utilization || []).map((p) => Number(p.utilization_pct || 0))
const dist = (props.chart?.series?.dist_utilization || []).map((p) => Number(p.utilization_pct || 0))
const n = Math.max(mfg.length, dist.length, 1)
const maxY = 120
const limitY = h - pad - (100 / maxY) * (h - pad * 2)
const toPoints = (arr) =>
  arr
    .map((v, i) => {
      const x = pad + (i * (w - pad * 2)) / Math.max(1, n - 1)
      const y = h - pad - (v / maxY) * (h - pad * 2)
      return `${x},${y}`
    })
    .join(' ')
</script>

<style scoped>
.chart-card { border: 1px solid var(--border); padding: 8px; border-radius: 6px; background: var(--bg-elev); }
.title { font-size: 11px; margin-bottom: 6px; color: var(--muted); }
.svg { width: 100%; height: 180px; background: var(--bg-soft); border: 1px solid var(--border); }
.axis { stroke: var(--border); stroke-width: 1; }
.limit { stroke: #d50000; stroke-width: 1.5; stroke-dasharray: 4 4; }
.line { fill: none; stroke-width: 2; }
.mfg { stroke: #ef5350; }
.dist { stroke: #ffa726; }
</style>
