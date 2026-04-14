<template>
  <div class="workbench-panel">
    <div class="report-layout">
      <div class="report-left">
        <div class="section-card">
          <div class="section-title">Report Summary</div>
          <p>{{ report?.executive_summary || 'Generate report from the latest run.' }}</p>
        </div>
        <div class="section-card">
          <div class="section-title">Actions</div>
          <ul>
            <li v-for="(action, idx) in (report?.actions || [])" :key="idx">{{ action }}</li>
          </ul>
        </div>
      </div>
      <div class="report-right">
        <div class="section-card">
          <div class="section-title">Decision</div>
          <p>Status: <b>{{ report?.decision?.status || '-' }}</b></p>
          <p>Bullwhip detected: <b>{{ report?.decision?.bullwhip_detected ? 'YES' : 'NO' }}</b></p>
          <p>Peak node: <b>{{ report?.decision?.peak_node || '-' }}</b></p>
          <p>Cause: <b>{{ report?.decision?.root_cause || '-' }}</b></p>
          <p>Recommendation: <b>{{ report?.decision?.recommendation || '-' }}</b></p>
          <div v-if="(report?.decision?.evidence || []).length">
            <p><b>Evidence:</b></p>
            <ul>
              <li v-for="(line, idx) in report?.decision?.evidence || []" :key="`ev-${idx}`">{{ line }}</li>
            </ul>
          </div>
        </div>
        <div class="section-card">
          <div class="section-title">Metrics</div>
          <p>Backlog: <b>{{ report?.metrics?.system_backlog ?? '-' }}</b></p>
          <p>Instability: <b>{{ report?.metrics?.instability_index ?? '-' }}</b></p>
          <p>Amplification DIST/RET: <b>{{ report?.metrics?.amplification_ratios?.dist_over_ret ?? '-' }}</b></p>
          <p>Amplification MFG/DIST: <b>{{ report?.metrics?.amplification_ratios?.mfg_over_dist ?? '-' }}</b></p>
          <p>Amplification SUP/MFG: <b>{{ report?.metrics?.amplification_ratios?.sup_over_mfg ?? '-' }}</b></p>
          <p>Margin impact: <b>{{ report?.metrics?.net_margin_impact ?? '-' }}</b></p>
        </div>
        <button class="action-btn" :disabled="!report" @click="$emit('next-step')">Go to explore →</button>
        <button class="action-btn secondary" :disabled="!report" @click="$emit('open-visualization')">Open visualization dashboard →</button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineEmits(['next-step', 'open-visualization'])
defineProps({ report: Object })
</script>

<style scoped>
.workbench-panel { height: 100%; background: #fafafa; overflow: hidden; padding: 24px; }
.report-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; height: 100%; }
.report-left,.report-right { display: flex; flex-direction: column; gap: 16px; }
.section-card { background: #fff; border: 1px solid #eaeaea; border-radius: 8px; padding: 16px; font-size: 13px; color: #444; line-height: 1.5; }
.section-title { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #777; margin-bottom: 8px; }
.action-btn { width: 100%; border: 0; background: #000; color: #fff; padding: 12px; border-radius: 4px; cursor: pointer; font-family: 'JetBrains Mono', monospace; margin-top: auto; }
.action-btn:disabled { background: #ddd; color: #888; cursor: not-allowed; }
.secondary { background: #121212; margin-top: 8px; }
</style>
