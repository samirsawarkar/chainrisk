<template>
  <div class="pro-root">
    <div v-if="loadError" class="banner">{{ loadError }}</div>
    <div v-else-if="loading && !bullData" class="banner">Loading workspace…</div>
    <section class="top">
      <BullwhipPro
        :dataset="bullMerged"
        :sku-filter="store.skuFilter"
        @sku-change="onSku"
        @brush-range="onBrush"
      />
    </section>
    <section class="mid">
      <CapacityHeatmap class="hm" :heatmap="heatData" :preview-matrix="previewHeatMatrix" @select-cell="onHeatCell" />
      <FlowNetworkPro
        class="fn"
        :flow="flowData"
        :model-tick="store.currentTick"
        :highlight-tokens="store.highlightTokens"
        @update:tick="onFlowTick"
        @select-node="onFlowSelect"
      />
    </section>
    <section class="bot">
      <CausalityExplorer :payload="causeData" @highlight="onHighlight" />
      <WhatIfPanel
        :start-tick="store.startTick"
        :end-tick="store.endTick"
        @applied="onWhatIf"
        @cleared="onWhatIfClear"
      />
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useCapeProStore } from '../../stores/capeProWorkspace'
import {
  getBullwhipProVisual,
  getCapacityHeatmapVisual,
  getCausalityChainVisual,
  getFlowNetworkVisual,
  getLatestSupplyChainReport,
} from '../../api/capeProject'
import BullwhipPro from './BullwhipPro.vue'
import CapacityHeatmap from './CapacityHeatmap.vue'
import FlowNetworkPro from './FlowNetworkPro.vue'
import CausalityExplorer from './CausalityExplorer.vue'
import WhatIfPanel from './WhatIfPanel.vue'

const store = useCapeProStore()
const loading = ref(false)
const loadError = ref('')
const bullData = ref(null)
const heatData = ref(null)
const flowData = ref(null)
const causeData = ref(null)

const bullMerged = computed(() => {
  const b = bullData.value
  if (!b) return null
  const p = store.lastWhatIf?.preview
  if (!p) return b
  return { ...b, preview: p }
})

const previewHeatMatrix = computed(() => store.lastWhatIf?.preview?.capacity_matrix_relaxed || null)

async function refresh() {
  loading.value = true
  loadError.value = ''
  const st = store.startTick
  const en = store.endTick
  const sku = store.skuFilter || undefined
  const node = store.selectedNodeId || 'DIST-01'
  const ct = store.currentTick
  try {
    const [b, h, f, c] = await Promise.all([
      getBullwhipProVisual({ start_tick: st, end_tick: en, sku }),
      getCapacityHeatmapVisual({ start_tick: st, end_tick: en }),
      getFlowNetworkVisual({ tick: ct, sku }),
      getCausalityChainVisual({ node_id: node, start_tick: st, end_tick: en }),
    ])
    bullData.value = b.data
    heatData.value = h.data
    flowData.value = f.data
    causeData.value = c.data
  } catch (e) {
    loadError.value = e?.message || 'Failed to load Pro workspace'
    bullData.value = null
    heatData.value = null
    flowData.value = null
    causeData.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => [store.startTick, store.endTick, store.skuFilter, store.currentTick, store.selectedNodeId],
  () => {
    refresh()
  }
)

onMounted(async () => {
  try {
    const rep = await getLatestSupplyChainReport()
    const t = rep.data?.tick ?? 0
    store.bootstrap(t)
  } catch {
    store.bootstrap(8)
  }
  await refresh()
})

function onSku(s) {
  store.setSku(s)
}

function onBrush(lo, hi) {
  store.setRange(lo, hi)
}

function onHeatCell({ node_id, tick }) {
  store.setSelectedNode(node_id)
  store.setCurrentTick(tick)
}

function onFlowTick(t) {
  store.setCurrentTick(t)
}

function onFlowSelect({ type, node }) {
  if (type === 'node' && node?.id) store.setSelectedNode(node.id)
}

function onHighlight(tokens) {
  store.setHighlightTokens(tokens)
}

function onWhatIf(data) {
  store.setWhatIf(data)
}

function onWhatIfClear() {
  store.clearWhatIf()
}
</script>

<style scoped>
.pro-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 480px;
}
.banner {
  padding: 10px;
  background: #fff8e1;
  border-radius: 6px;
  font-size: 12px;
}
.top {
  width: 100%;
}
.mid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  align-items: start;
}
@media (max-width: 960px) {
  .mid {
    grid-template-columns: 1fr;
  }
}
.bot {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 960px) {
  .bot {
    grid-template-columns: 1fr;
  }
}
</style>
