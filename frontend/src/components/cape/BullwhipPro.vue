<template>
  <div class="bw-pro">
    <div class="bw-head">
      <span class="title">Bullwhip analyzer</span>
      <label class="sku-toggle"><input type="checkbox" :checked="skuAll" @change="toggleSkuAll" /> All SKUs scenario</label>
      <label class="sku-toggle"><input type="checkbox" :checked="skuA" @change="emitSku('A')" /> SKU A</label>
      <label class="sku-toggle"><input type="checkbox" :checked="skuB" @change="emitSku('B')" /> SKU B</label>
    </div>
    <div ref="chartEl" class="chart" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  dataset: { type: Object, default: null },
  /** Sync checkboxes from Pinia (A/B/'' ) */
  skuFilter: { type: String, default: '' },
})

const emit = defineEmits(['sku-change', 'brush-range'])

const chartEl = ref(null)
let chart = null
const skuAll = ref(true)
const skuA = ref(false)
const skuB = ref(false)

watch(
  () => props.skuFilter,
  (v) => {
    skuAll.value = !v
    skuA.value = v === 'A'
    skuB.value = v === 'B'
  },
  { immediate: true }
)

const skuForApi = computed(() => {
  if (skuA.value && !skuB.value) return 'A'
  if (skuB.value && !skuA.value) return 'B'
  return ''
})

function toggleSkuAll() {
  skuAll.value = true
  skuA.value = false
  skuB.value = false
  emit('sku-change', '')
}

function emitSku(sku) {
  skuAll.value = false
  if (sku === 'A') {
    skuA.value = !skuA.value
    if (skuA.value) skuB.value = false
  } else {
    skuB.value = !skuB.value
    if (skuB.value) skuA.value = false
  }
  if (!skuA.value && !skuB.value) {
    skuAll.value = true
    emit('sku-change', '')
  } else {
    emit('sku-change', skuForApi.value)
  }
}

function buildOption() {
  const d = props.dataset
  if (!d?.ticks?.length) {
    return {
      title: { text: 'No simulation data', left: 'center', top: 'middle', textStyle: { fontSize: 12 } },
    }
  }
  const ticks = d.ticks
  const s = d.series || {}
  const adj = d.preview?.ret_scenario_adjusted
  const series = [
    { name: 'RET scenario demand', type: 'line', smooth: true, showSymbol: false, data: s.ret_scenario || [] },
    { name: 'RET orders', type: 'line', smooth: true, showSymbol: false, data: s.ret_orders || [] },
    { name: 'DIST orders', type: 'line', smooth: true, showSymbol: false, data: s.dist_orders || [] },
    { name: 'MFG orders', type: 'line', smooth: true, showSymbol: false, data: s.mfg_orders || [] },
    {
      name: 'RET→DIST amp',
      type: 'line',
      yAxisIndex: 1,
      smooth: true,
      showSymbol: false,
      lineStyle: { type: 'dotted' },
      data: s.ret_dist_amplification || [],
    },
  ]
  if (adj && adj.length === ticks.length) {
    series.push({
      name: 'RET scenario (what-if)',
      type: 'line',
      smooth: true,
      showSymbol: false,
      lineStyle: { type: 'dashed' },
      data: adj,
    })
  }
  const adjAmp = d.preview?.ret_dist_amplification_adjusted
  if (adjAmp && adjAmp.length === ticks.length) {
    series.push({
      name: 'RET→DIST amp (what-if)',
      type: 'line',
      yAxisIndex: 1,
      smooth: true,
      showSymbol: false,
      lineStyle: { type: 'dashed', width: 1 },
      data: adjAmp,
    })
  }
  return {
    tooltip: {
      trigger: 'axis',
      formatter(params) {
        const tick = params[0]?.axisValue
        const lines = params.map((p) => `${p.marker}${p.seriesName}: ${p.data ?? p.value}`)
        const i = ticks.indexOf(Number(tick))
        if (i >= 0 && s.ret_dist_amplification?.[i] != null) {
          lines.push(`amp (canonical tick): ${Number(s.ret_dist_amplification[i]).toFixed(3)}×`)
        }
        return [`Tick ${tick}`, ...lines].join('<br/>')
      },
    },
    legend: { type: 'scroll', bottom: 0, textStyle: { fontSize: 10 } },
    grid: { left: 48, right: 48, top: 28, bottom: 56 },
    xAxis: { type: 'category', data: ticks, boundaryGap: false },
    yAxis: [
      { type: 'value', name: 'Qty', splitLine: { show: true, lineStyle: { opacity: 0.15 } } },
      { type: 'value', name: 'Amp×', splitLine: { show: false }, min: 0.8 },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
      { type: 'slider', xAxisIndex: 0, height: 18, bottom: 28, filterMode: 'none' },
    ],
    brush: { toolbox: ['lineX', 'clear'], xAxisIndex: 0 },
    toolbox: { feature: { brush: { type: ['lineX'] }, restore: {}, saveAsImage: {} } },
    series,
  }
}

function render() {
  if (!chart || !props.dataset) return
  chart.setOption(buildOption(), true)
}

watch(
  () => props.dataset,
  () => {
    if (chart) render()
  },
  { deep: true }
)

onMounted(() => {
  if (!chartEl.value) return
  chart = echarts.init(chartEl.value)
  chart.setOption(buildOption())
  chart.on('datazoom', (ev) => {
    const ticks = props.dataset?.ticks || []
    if (!ticks.length) return
    const batch = ev?.batch?.[0]
    const opt = chart.getOption()
    const dz0 = batch || opt.dataZoom?.[0] || {}
    let i0 = 0
    let i1 = ticks.length - 1
    if (dz0.startValue != null && dz0.endValue != null) {
      i0 = Math.max(0, Math.floor(Number(dz0.startValue)))
      i1 = Math.min(ticks.length - 1, Math.ceil(Number(dz0.endValue)))
    } else if (dz0.start != null && dz0.end != null) {
      i0 = Math.max(0, Math.floor((dz0.start / 100) * (ticks.length - 1)))
      i1 = Math.min(ticks.length - 1, Math.ceil((dz0.end / 100) * (ticks.length - 1)))
    }
    if (ticks[i0] != null && ticks[i1] != null) emit('brush-range', ticks[i0], ticks[i1])
  })
  window.addEventListener('resize', resize)
})

function resize() {
  chart?.resize()
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.bw-pro {
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 8px;
  background: var(--bg-elev, #fff);
  padding: 8px;
}
.bw-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}
.title {
  font-weight: 700;
  font-size: 12px;
}
.sku-toggle {
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}
.chart {
  width: 100%;
  height: 320px;
}
</style>
