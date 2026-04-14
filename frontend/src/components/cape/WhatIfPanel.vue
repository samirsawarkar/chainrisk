<template>
  <div class="wf">
    <div class="wf-head">
      <span class="title">What-if simulator</span>
      <button type="button" class="btn" :disabled="loading" @click="run">Apply</button>
      <button type="button" class="btn ghost" :disabled="loading" @click="clear">Reset preview</button>
    </div>
    <label>SKU <select v-model="sku"><option value="B">B</option><option value="A">A</option></select></label>
    <label>Demand Δ % <input v-model.number="demandPct" type="range" min="-40" max="20" step="1" /> {{ demandPct }}%</label>
    <label>Capacity relax % <input v-model.number="capRelax" type="range" min="0" max="40" step="1" /> {{ capRelax }}%</label>
    <label>Amp overlay × <input v-model.number="ampOv" type="range" min="0.7" max="1.3" step="0.02" /> {{ ampOv.toFixed(2) }}</label>
    <div v-if="error" class="err">{{ error }}</div>
    <div v-if="last?.counterfactual" class="out">
      <div>amp baseline → CF: {{ last.counterfactual.amplification_baseline }} → {{ last.counterfactual.amplification_counterfactual }}</div>
      <div>backlog Δ (model): {{ last.counterfactual.backlog_change }} · instability Δ: {{ last.counterfactual.instability_change }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { postSimulateAdjustment } from '../../api/capeProject'

const props = defineProps({
  startTick: { type: Number, default: 0 },
  endTick: { type: Number, default: 8 },
})

const emit = defineEmits(['applied', 'cleared'])

const sku = ref('B')
const demandPct = ref(-15)
const capRelax = ref(0)
const ampOv = ref(1)
const loading = ref(false)
const error = ref('')
const last = ref(null)

async function run() {
  error.value = ''
  loading.value = true
  try {
    const res = await postSimulateAdjustment({
      sku: sku.value,
      demand_percent: demandPct.value,
      capacity_relax_pct: capRelax.value,
      amplification_overlay: ampOv.value,
      start_tick: props.startTick,
      end_tick: props.endTick,
    })
    last.value = res.data
    emit('applied', res.data)
  } catch (e) {
    error.value = e?.message || 'Request failed'
  } finally {
    loading.value = false
  }
}

function clear() {
  last.value = null
  emit('cleared')
}
</script>

<style scoped>
.wf {
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 8px;
  background: var(--bg-elev, #fff);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 11px;
}
.wf-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.title {
  font-weight: 700;
  flex: 1;
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
input[type='range'] {
  width: 100%;
}
.btn {
  border: 0;
  background: #111;
  color: #fff;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn.ghost {
  background: #eee;
  color: #111;
}
.err {
  color: #b00020;
}
.out {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #333;
}
</style>
