<template>
  <div class="chart-card">
    <div class="title">Bullwhip</div>
    <svg :viewBox="`0 0 ${w} ${h}`" class="svg">
      <line :x1="pad" :y1="h-pad" :x2="w-pad" :y2="h-pad" class="axis" />
      <line :x1="pad" :y1="pad" :x2="pad" :y2="h-pad" class="axis" />
      <polyline :points="toPoints(ret)" class="line ret" />
      <polyline :points="toPoints(dist)" class="line dist" />
      <polyline :points="toPoints(mfg)" class="line mfg" />
    </svg>
  </div>
</template>

<script setup>
const props = defineProps({ chart: { type: Object, default: () => ({}) } })
const w = 420
const h = 200
const pad = 22
const ret = (props.chart?.series?.ret_demand || []).map((p) => Number(p.qty || 0))
const dist = (props.chart?.series?.dist_orders || []).map((p) => Number(p.qty || 0))
const mfg = (props.chart?.series?.mfg_orders || []).map((p) => Number(p.qty || 0))
const n = Math.max(ret.length, dist.length, mfg.length, 1)
const maxY = Math.max(1, ...ret, ...dist, ...mfg)
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
.line { fill: none; stroke-width: 2; }
.ret { stroke: #4dd0e1; }
.dist { stroke: #ffa726; }
.mfg { stroke: #ef5350; }
</style>
