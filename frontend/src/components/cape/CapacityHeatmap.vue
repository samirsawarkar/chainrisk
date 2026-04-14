<template>
  <div class="hm-wrap">
    <div class="hm-head">
      <span class="title">Capacity heatmap</span>
      <span class="muted">click cell for detail</span>
    </div>
    <div ref="chartEl" class="chart" />
    <div v-if="detail" class="detail">
      <div class="detail-title">{{ detail.node_id }} · T{{ detail.tick }}</div>
      <div class="detail-cap">Utilization {{ detail.capacity_utilization_pct }}%</div>
      <table>
        <thead><tr><th>SKU</th><th>On hand</th><th>Backlog</th><th>Inbound orders</th></tr></thead>
        <tbody>
          <tr v-for="row in detail.sku_split || []" :key="row.sku_id">
            <td>{{ row.sku_id }}</td><td>{{ row.on_hand }}</td><td>{{ row.backlog }}</td><td>{{ row.incoming_orders }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="(detail.retail_scenario || []).length" class="scen">
        <div class="sub">Retail scenario (node is RET)</div>
        <div v-for="r in detail.retail_scenario" :key="r.sku_id">{{ r.sku_id }}: {{ r.scenario_demand }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { getCapacityNodeDetail } from '../../api/capeProject'

const props = defineProps({
  heatmap: { type: Object, default: null },
  /** Optional relaxed matrix from what-if preview */
  previewMatrix: { type: Array, default: null },
})

const emit = defineEmits(['select-cell'])

const chartEl = ref(null)
let chart = null
const detail = ref(null)

function utilColor(v) {
  if (v < 70) return '#2e7d32'
  if (v <= 90) return '#f9a825'
  return '#c62828'
}

function buildOption() {
  const h = props.heatmap
  if (!h?.nodes?.length || !h?.ticks?.length) {
    return { title: { text: 'No capacity rows', left: 'center', top: 'middle', textStyle: { fontSize: 11 } } }
  }
  const nodes = h.nodes
  const ticks = h.ticks
  const matrix = props.previewMatrix && props.previewMatrix.length === nodes.length ? props.previewMatrix : h.matrix
  const cells = []
  nodes.forEach((n, yi) => {
    ticks.forEach((t, xi) => {
      const v = matrix[yi]?.[xi] ?? 0
      cells.push([xi, yi, Math.round(v * 100) / 100])
    })
  })
  return {
    tooltip: {
      position: 'top',
      formatter(p) {
        const xi = p.data[0]
        const yi = p.data[1]
        const v = p.data[2]
        return `${nodes[yi]?.id} · T${ticks[xi]}<br/>${v}%`
      },
    },
    grid: { left: 72, right: 12, top: 8, bottom: 28 },
    xAxis: { type: 'category', data: ticks.map((t) => `T${t}`), splitArea: { show: true } },
    yAxis: { type: 'category', data: nodes.map((n) => n.id), splitArea: { show: true } },
    visualMap: {
      min: 0,
      max: 100,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 2,
      inRange: { color: ['#e8f5e9', '#fff9c4', '#ffcdd2'] },
    },
    series: [
      {
        name: 'util',
        type: 'heatmap',
        data: cells,
        label: { show: false },
        emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.35)' } },
        itemStyle: {
          borderWidth: 1,
          borderColor: '#fff',
        },
      },
    ],
  }
}

async function onClick(params) {
  if (params.componentType !== 'series' || !props.heatmap) return
  const xi = params.data[0]
  const yi = params.data[1]
  const node = props.heatmap.nodes[yi]?.id
  const tick = props.heatmap.ticks[xi]
  if (!node || tick == null) return
  emit('select-cell', { node_id: node, tick })
  try {
    const res = await getCapacityNodeDetail({ node_id: node, tick })
    detail.value = res.data
  } catch {
    detail.value = { node_id: node, tick, sku_split: [], capacity_utilization_pct: params.data[2] }
  }
}

function render() {
  if (!chart) return
  chart.setOption(buildOption(), true)
  chart.off('click')
  chart.on('click', onClick)
}

watch(
  () => [props.heatmap, props.previewMatrix],
  () => render(),
  { deep: true }
)

onMounted(() => {
  chart = echarts.init(chartEl.value)
  render()
  window.addEventListener('resize', () => chart?.resize())
})

onBeforeUnmount(() => {
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.hm-wrap {
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 8px;
  background: var(--bg-elev, #fff);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hm-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title {
  font-weight: 700;
  font-size: 12px;
}
.muted {
  font-size: 10px;
  color: #888;
}
.chart {
  width: 100%;
  height: 260px;
}
.detail {
  font-size: 11px;
  border-top: 1px solid #eee;
  padding-top: 8px;
  max-height: 180px;
  overflow: auto;
}
.detail-title {
  font-weight: 700;
  margin-bottom: 4px;
}
.detail-cap {
  margin-bottom: 6px;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  border: 1px solid #eee;
  padding: 4px 6px;
  text-align: left;
}
.scen {
  margin-top: 6px;
}
.sub {
  font-weight: 600;
  margin-bottom: 4px;
}
</style>
