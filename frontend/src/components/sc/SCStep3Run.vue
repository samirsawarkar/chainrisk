<template>
  <div class="workbench-panel">
    <div class="scroll-container">
      <div class="step-card">
        <div class="card-header"><div class="step-info"><span class="step-num">01</span><span class="step-title">Run Simulation</span></div><span class="badge" :class="runStatusClass">{{ runStatus }}</span></div>
        <p class="api-note">POST /api/cape/run · GET /api/cape/run-status</p>
        <p class="description">{{ runMessage }}</p>
        <button class="action-btn" :disabled="running" @click="$emit('run')">{{ running ? 'Running...' : 'Run supply chain simulation' }}</button>
      </div>

      <div class="step-card">
        <div class="card-header"><div class="step-info"><span class="step-num">02</span><span class="step-title">Tick Timeline</span></div></div>
        <div class="timeline">
          <div class="timeline-row" v-for="(ev, idx) in events" :key="idx">
            <span class="tick">T{{ ev.tick }}</span>
            <span class="msg">{{ ev.message }}</span>
          </div>
        </div>
      </div>

      <div class="step-card">
        <div class="card-header"><div class="step-info"><span class="step-num">03</span><span class="step-title">Decision Signal</span></div></div>
        <p class="description">Status: <b>{{ decision?.status || '-' }}</b> · Root cause: <b>{{ decision?.root_cause || '-' }}</b></p>
        <p class="description">Bullwhip: <b>{{ decision?.bullwhip_detected ? 'DETECTED' : 'NOT DETECTED' }}</b> · Peak node: <b>{{ decision?.peak_node || '-' }}</b></p>
        <p class="description">Recommendation: <b>{{ decision?.recommendation || '-' }}</b></p>
        <button class="action-btn" :disabled="!decision" @click="$emit('next-step')">Generate report →</button>
      </div>
    </div>
    <div class="system-logs">
      <div class="log-header"><span>SYSTEM DASHBOARD</span><span>SC-STEP3</span></div>
      <div class="log-content">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx"><span class="log-time">{{ log.time }}</span><span>{{ log.msg }}</span></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
defineEmits(['run', 'next-step'])
const props = defineProps({
  running: Boolean,
  runStatus: { type: String, default: 'idle' },
  runMessage: { type: String, default: '' },
  events: { type: Array, default: () => [] },
  decision: Object,
  systemLogs: { type: Array, default: () => [] },
})

const runStatusClass = computed(() => {
  if (props.runStatus === 'completed') return 'success'
  if (props.runStatus === 'failed') return 'error'
  return 'processing'
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
.description { font-size: 12px; color: #666; margin-bottom: 8px; line-height: 1.5; }
.badge { font-size: 10px; padding: 4px 8px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
.badge.success { background: #e8f5e9; color: #2e7d32; }
.badge.processing { background: #ff5722; color: #fff; }
.badge.error { background: #ffebee; color: #c62828; }
.timeline { max-height: 180px; overflow-y: auto; border: 1px solid #eee; border-radius: 6px; background: #fafafa; }
.timeline-row { padding: 8px 10px; border-bottom: 1px solid #eee; display: flex; gap: 10px; font-size: 12px; }
.tick { font-family: 'JetBrains Mono', monospace; color: #111; min-width: 40px; }
.msg { color: #666; }
.action-btn { width: 100%; border: 0; background: #000; color: #fff; padding: 12px; border-radius: 4px; cursor: pointer; font-family: 'JetBrains Mono', monospace; }
.action-btn:disabled { background: #ddd; color: #888; cursor: not-allowed; }
.system-logs { background: #000; color: #ddd; padding: 14px; font-family: 'JetBrains Mono', monospace; }
.log-header { display: flex; justify-content: space-between; border-bottom: 1px solid #333; padding-bottom: 8px; margin-bottom: 8px; font-size: 10px; }
.log-content { max-height: 90px; overflow-y: auto; }
.log-line { font-size: 11px; display: flex; gap: 10px; line-height: 1.5; }
.log-time { color: #666; min-width: 74px; }
</style>
