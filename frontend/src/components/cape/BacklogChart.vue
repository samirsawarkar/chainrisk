<template>
  <div class="chart-card">
    <div class="title">Backlog</div>
    <svg :viewBox="`0 0 ${w} ${h}`" class="svg">
      <line :x1="pad" :y1="h-pad" :x2="w-pad" :y2="h-pad" class="axis" />
      <line :x1="pad" :y1="pad" :x2="pad" :y2="h-pad" class="axis" />
      <polyline :points="toPoints(values)" class="line bkg" />
    </svg>
  </div>
</template>

<script setup>
const props = defineProps({ chart: { type: Object, default: () => ({}) } })
const w = 420
const h = 200
const pad = 22
const values = (props.chart?.series || []).map((p) => Number(p.backlog || 0))
const n = Math.max(values.length, 1)
const maxY = Math.max(1, ...values)
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
.bkg { stroke: #ab47bc; }
</style>
