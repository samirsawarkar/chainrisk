<template>
  <div class="workbench-panel">
    <div class="scroll-container">
      <div class="step-card">
        <div class="card-header"><div class="step-info"><span class="step-num">01</span><span class="step-title">Agent Setup</span></div><span class="badge success" v-if="setupData">READY</span></div>
        <p class="api-note">POST /api/cape/setup/create</p>
        <p class="description">Generate node operators and execution schedule.</p>
        <button class="action-btn" :disabled="loading" @click="$emit('build-setup')">{{ loading ? 'Creating...' : 'Create setup' }}</button>
      </div>

      <div class="step-card">
        <div class="card-header"><div class="step-info"><span class="step-num">02</span><span class="step-title">Personas</span></div></div>
        <div class="persona-grid">
          <div class="persona" v-for="agent in (setupData?.agents || [])" :key="agent.agent_id">
            <div class="persona-id">{{ agent.agent_id }}</div>
            <div class="persona-role">{{ agent.role }}</div>
            <div class="persona-node">{{ agent.node_id }}</div>
          </div>
        </div>
      </div>

      <div class="step-card">
        <div class="card-header"><div class="step-info"><span class="step-num">03</span><span class="step-title">Input Consistency</span></div><span class="badge" :class="consistency?.valid ? 'success' : 'processing'">{{ consistency?.valid ? 'PASS' : 'CHECK' }}</span></div>
        <p class="api-note">POST /api/cape/input/consistency-check</p>
        <p class="description">{{ consistencyText }}</p>
        <button class="action-btn" :disabled="!canContinue" @click="$emit('next-step')">Start simulation →</button>
      </div>
    </div>
    <div class="system-logs">
      <div class="log-header"><span>SYSTEM DASHBOARD</span><span>SC-STEP2</span></div>
      <div class="log-content">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx"><span class="log-time">{{ log.time }}</span><span>{{ log.msg }}</span></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
defineEmits(['build-setup', 'next-step'])
const props = defineProps({
  loading: Boolean,
  setupData: Object,
  consistency: Object,
  systemLogs: { type: Array, default: () => [] },
})

const canContinue = computed(() => !!props.setupData && !!props.consistency?.valid)
const consistencyText = computed(() => {
  if (!props.consistency) return 'Run consistency check after setup is generated.'
  if (props.consistency.valid) return 'Config and scenario are aligned.'
  return (props.consistency.errors || []).join(', ') || 'Consistency check failed.'
})
</script>

<style scoped>
.workbench-panel { height: 100%; background: #fafafa; display: flex; flex-direction: column; overflow: hidden; }
.scroll-container { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.step-card { background: #fff; border: 1px solid #eaeaea; border-radius: 8px; padding: 18px; }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.step-info { display: flex; align-items: center; gap: 10px; }
.step-num { font-family: 'JetBrains Mono', monospace; color: #bdbdbd; font-weight: 700; }
.step-title { font-weight: 600; }
.api-note { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #999; margin-bottom: 8px; }
.description { font-size: 12px; color: #666; margin-bottom: 12px; line-height: 1.5; }
.badge { font-size: 10px; padding: 4px 8px; border-radius: 4px; font-weight: 600; }
.badge.success { background: #e8f5e9; color: #2e7d32; }
.badge.processing { background: #ff5722; color: #fff; }
.persona-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.persona { background: #f6f6f6; border-radius: 6px; padding: 10px; }
.persona-id { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #111; }
.persona-role { font-weight: 700; font-size: 12px; }
.persona-node { color: #777; font-size: 11px; }
.action-btn { width: 100%; border: 0; background: #000; color: #fff; padding: 12px; border-radius: 4px; cursor: pointer; font-family: 'JetBrains Mono', monospace; }
.action-btn:disabled { background: #ddd; color: #888; cursor: not-allowed; }
.system-logs { background: #000; color: #ddd; padding: 14px; font-family: 'JetBrains Mono', monospace; }
.log-header { display: flex; justify-content: space-between; border-bottom: 1px solid #333; padding-bottom: 8px; margin-bottom: 8px; font-size: 10px; }
.log-content { max-height: 90px; overflow-y: auto; }
.log-line { font-size: 11px; display: flex; gap: 10px; line-height: 1.5; }
.log-time { color: #666; min-width: 74px; }
</style>
