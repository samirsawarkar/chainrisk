<template>
  <div class="chart-card">
    <div class="title">Flow Diagram</div>
    <div v-if="chainLine" class="chain-line">{{ chainLine }} · T{{ endTick }}</div>
    <div v-if="stages.length" class="stages">
      <div v-for="s in stages" :key="s.id" class="stage">
        <div class="stage-id">{{ s.id }}</div>
        <div class="stage-stats">
          <span>demand {{ s.demand }}</span>
          <span>order {{ s.order }}</span>
          <span v-if="s.backlog != null && s.backlog !== undefined">backlog {{ s.backlog }}</span>
          <span v-if="s.amplification_pct > 0">amp {{ s.amplification_pct }}%</span>
        </div>
      </div>
    </div>
    <div v-if="edgeLabels.length" class="edge-lines">
      <div v-for="(line, i) in edgeLabels" :key="`e-${i}`" class="edge-line">{{ line }}</div>
    </div>
    <div v-else class="flow-wrap">
      <div v-for="node in legacyNodes" :key="node.id" class="node">{{ node.label }}</div>
    </div>
    <div v-if="edges.length && !stages.length" class="edge-list">
      <div v-for="(edge, idx) in edges.slice(0, 6)" :key="idx" class="edge-item">
        {{ edge.source }} → {{ edge.target }} · {{ edge.sku_id }} · q={{ edge.weight }} · T{{ edge.tick }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ diagram: { type: Object, default: () => ({}) } })

const stages = computed(() => props.diagram?.stages || [])
const chainLine = computed(() => props.diagram?.chain_line || '')
const endTick = computed(() => props.diagram?.end_tick ?? '')
const legacyNodes = computed(() => props.diagram?.nodes || [])
const edges = computed(() => props.diagram?.edges || [])
const edgeLabels = computed(() => {
  const e = props.diagram?.edges || []
  return e.map((x) => x.label || `${x.source} → ${x.target}: ${x.demand} → ${x.orders} (${Number(x.ratio || 0).toFixed(2)}×)`)
})
</script>

<style scoped>
.chart-card { border: 1px solid var(--border); padding: 8px; border-radius: 6px; background: var(--bg-elev); }
.title { font-size: 11px; margin-bottom: 6px; color: var(--muted); }
.chain-line { font-size: 11px; color: var(--muted); margin-bottom: 10px; font-family: 'JetBrains Mono', monospace; }
.stages { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; margin-bottom: 8px; }
.stage { border: 1px solid var(--border); background: var(--bg-soft); border-radius: 6px; padding: 8px; }
.stage-id { font-weight: 700; font-size: 12px; margin-bottom: 6px; }
.stage-stats { display: flex; flex-direction: column; gap: 2px; font-size: 10px; color: var(--muted); font-family: 'JetBrains Mono', monospace; }
.flow-wrap { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.node { border: 1px solid var(--border); background: var(--bg-soft); padding: 4px 8px; font-size: 11px; border-radius: 4px; }
.edge-list { max-height: 120px; overflow: auto; border-top: 1px solid var(--border); padding-top: 6px; }
.edge-item { font-size: 11px; color: var(--muted); margin-bottom: 4px; }
.edge-lines { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
.edge-line { font-size: 10px; color: var(--muted); font-family: 'JetBrains Mono', monospace; margin-bottom: 4px; }
</style>
