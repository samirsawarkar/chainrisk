<template>
  <div class="workbench-panel">
    <div class="scroll-container">
      <div class="step-card" :class="{ active: true, completed: valid }">
        <div class="card-header">
          <div class="step-info"><span class="step-num">01</span><span class="step-title">Validate Config</span></div>
          <span class="badge" :class="valid ? 'success' : 'processing'">{{ valid ? 'VALID' : 'PENDING' }}</span>
        </div>
        <div class="card-content">
          <p class="api-note">POST /api/cape/validate-config</p>
          <p class="description">{{ validationMessage }}</p>
        </div>
      </div>

      <div class="step-card" :class="{ completed: built }">
        <div class="card-header">
          <div class="step-info"><span class="step-num">02</span><span class="step-title">Build Graph</span></div>
          <span class="badge" :class="built ? 'success' : 'processing'">{{ built ? 'READY' : 'WAITING' }}</span>
        </div>
        <div class="card-content">
          <p class="api-note">POST /api/cape/graph/build</p>
          <p class="description">Builds node, edge, and SKU signal summary for GraphPanel.</p>
          <div class="stats-grid">
            <div class="stat-card"><span class="stat-value">{{ graphStats.nodes }}</span><span class="stat-label">NODES</span></div>
            <div class="stat-card"><span class="stat-value">{{ graphStats.edges }}</span><span class="stat-label">EDGES</span></div>
            <div class="stat-card"><span class="stat-value">{{ graphStats.skus }}</span><span class="stat-label">SKUS</span></div>
          </div>
          <button class="action-btn" :disabled="loading || !valid" @click="$emit('build-graph')">
            {{ loading ? 'Building...' : 'Build graph' }}
          </button>
        </div>
      </div>

      <div class="step-card">
        <div class="card-header">
          <div class="step-info"><span class="step-num">03</span><span class="step-title">Enter Setup</span></div>
        </div>
        <div class="card-content">
          <p class="api-note">NEXT STEP</p>
          <p class="description">Continue to setup once graph is built.</p>
          <button class="action-btn" :disabled="!built" @click="$emit('next-step')">Enter setup →</button>
        </div>
      </div>
    </div>
    <div class="system-logs">
      <div class="log-header"><span>SYSTEM DASHBOARD</span><span>SC-STEP1</span></div>
      <div class="log-content">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx"><span class="log-time">{{ log.time }}</span><span>{{ log.msg }}</span></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

defineEmits(['build-graph', 'next-step'])
const props = defineProps({
  valid: Boolean,
  built: Boolean,
  loading: Boolean,
  validationMessage: String,
  graphSummary: Object,
  systemLogs: { type: Array, default: () => [] },
})

const graphStats = computed(() => ({
  nodes: props.graphSummary?.node_count || 0,
  edges: props.graphSummary?.edge_count || 0,
  skus: props.graphSummary?.sku_count || 0,
}))
</script>

<style scoped>
.workbench-panel { height: 100%; background: #fafafa; display: flex; flex-direction: column; overflow: hidden; }
.scroll-container { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.step-card { background: #fff; border: 1px solid #eaeaea; border-radius: 8px; padding: 18px; }
.step-card.completed { border-color: #4caf50; }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.step-info { display: flex; gap: 10px; align-items: center; }
.step-num { font-family: 'JetBrains Mono', monospace; font-weight: 700; color: #bdbdbd; }
.step-title { font-weight: 600; }
.badge { font-size: 10px; padding: 4px 8px; border-radius: 4px; font-weight: 600; }
.badge.success { background: #e8f5e9; color: #2e7d32; }
.badge.processing { background: #ff5722; color: #fff; }
.api-note { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #999; margin-bottom: 8px; }
.description { font-size: 12px; color: #666; margin-bottom: 12px; line-height: 1.5; }
.stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 12px; }
.stat-card { background: #f6f6f6; border-radius: 6px; padding: 10px; text-align: center; }
.stat-value { font-family: 'JetBrains Mono', monospace; font-size: 18px; font-weight: 700; display: block; }
.stat-label { font-size: 10px; color: #888; }
.action-btn { width: 100%; border: 0; background: #000; color: #fff; padding: 12px; border-radius: 4px; cursor: pointer; font-family: 'JetBrains Mono', monospace; }
.action-btn:disabled { background: #ddd; color: #888; cursor: not-allowed; }
.system-logs { background: #000; color: #ddd; padding: 14px; font-family: 'JetBrains Mono', monospace; }
.log-header { display: flex; justify-content: space-between; border-bottom: 1px solid #333; padding-bottom: 8px; margin-bottom: 8px; font-size: 10px; }
.log-content { max-height: 90px; overflow-y: auto; }
.log-line { font-size: 11px; display: flex; gap: 10px; line-height: 1.5; }
.log-time { color: #666; min-width: 74px; }
</style>
