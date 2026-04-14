<template>
  <div class="home-container">
    <GlobalTopNav active="landing" />

    <div class="main-content">
      <section class="hero-section">
        <div class="hero-left">
          <img class="hero-logo" :src="heroLogo" alt="ChainRisk logo" />
          <div class="tag-row">
            <span class="orange-tag">SUPPLY CHAIN</span>
            <span class="version-text">v1.6 workflow</span>
          </div>
          <h1 class="main-title">
            Build your network,<br />
            <span class="gradient-text">simulate agent decisions</span>
          </h1>
          <div class="hero-desc">
            Configure system structure and scenario demand. Then run the ChainRisk-style Graph → Setup → Run → Report → Explore workflow for CAPE.
          </div>
          <p class="slogan-text">
            Realistic failures under delay and capacity constraints<span class="blinking-cursor">_</span>
          </p>
          <div class="decoration-square"></div>
        </div>
      </section>

      <section class="dashboard-section">
        <div class="left-panel">
          <div class="panel-header"><span class="status-dot">■</span> SYSTEM STATUS</div>
          <h2 class="section-title">{{ validConfig ? 'Ready' : 'Waiting for input' }}</h2>
          <p class="section-desc">{{ statusMessage }}</p>
          <div class="steps-container">
            <div class="steps-header"><span class="diamond-icon">◇</span> WORKFLOW SEQUENCE</div>
            <div class="workflow-list">
              <div class="workflow-item"><span class="step-num">01</span><div><div class="step-title">Graph</div><div class="step-desc">Build network graph from config + scenario.</div></div></div>
              <div class="workflow-item"><span class="step-num">02</span><div><div class="step-title">Setup</div><div class="step-desc">Generate chain agents and schedule.</div></div></div>
              <div class="workflow-item"><span class="step-num">03</span><div><div class="step-title">Run</div><div class="step-desc">Execute CAPE ticks with event flow.</div></div></div>
              <div class="workflow-item"><span class="step-num">04</span><div><div class="step-title">Report</div><div class="step-desc">Generate structured risk decision report.</div></div></div>
              <div class="workflow-item"><span class="step-num">05</span><div><div class="step-title">Analyze</div><div class="step-desc">Chat + Pro workspace on the same ledger metrics.</div></div></div>
            </div>
          </div>
        </div>

        <div class="right-panel">
          <div class="console-box">
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">SYSTEM CONFIG JSON</span>
                <span class="console-meta">{{ validConfig ? 'VALID' : 'PENDING' }}</span>
              </div>
              <div class="input-wrapper">
                <textarea v-model="systemText" class="code-input" rows="10"></textarea>
              </div>
              <button class="small-btn" @click="validateConfig">Validate config</button>
            </div>

            <div class="console-divider"><span>SCENARIO INPUT</span></div>

            <div class="console-section">
              <div class="console-header">
                <span class="console-label">CSV/EXCEL</span>
                <span class="console-meta">Rows: {{ scenarioRows }}</span>
              </div>
              <div class="upload-zone" @click="pickFile">
                <input ref="fileInput" type="file" accept=".csv,.xlsx,.xlsm" style="display:none" @change="onFile" />
                <div class="upload-placeholder">
                  <div class="upload-icon">↑</div>
                  <div class="upload-title">{{ fileName || 'Drop files here or choose files' }}</div>
                </div>
              </div>
            </div>

            <div class="console-section btn-section">
              <button class="start-engine-btn" :disabled="!canStart" @click="startProject">
                <span>Start project</span>
                <span class="btn-arrow">→</span>
              </button>
              <p class="cta-hint">{{ runMessage }}</p>
            </div>
          </div>
        </div>
      </section>

      <section class="history-section">
        <div class="history-header">
          <h3>Project History</h3>
          <button class="small-btn history-refresh" @click="loadHistory">Refresh history</button>
        </div>
        <div v-if="historyLoading" class="history-empty">Loading saved projects...</div>
        <div v-else-if="projectHistory.length === 0" class="history-empty">No saved projects yet.</div>
        <div v-else class="history-grid">
          <div v-for="item in projectHistory" :key="item.project_id" class="history-card">
            <div class="history-title">{{ item.project_name }}</div>
            <div class="history-meta">Status: {{ item.latest_status || 'draft' }} · Updated: {{ formatDate(item.updated_at) }}</div>
            <div class="history-meta">File: {{ item.scenario_file_name || '-' }}</div>
            <div class="history-meta">Backlog: {{ item.latest_visual_summary?.system_backlog ?? 0 }} · Instability: {{ item.latest_visual_summary?.instability_index ?? 0 }}</div>
            <button class="small-btn" @click="openProject(item.project_id)">Open project</button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import GlobalTopNav from '../components/sc/GlobalTopNav.vue'
import heroLogo from '../../image/logo-1.jpg'
import { setScSession } from '../store/scSession'
import { extractApiError } from '../api/errors'
import {
  getSupplyChainProjectById,
  getSupplyChainProjectHistory,
  saveSupplyChainProject,
  uploadScenarioFile,
  validateSystemConfig,
} from '../api/capeProject'

const router = useRouter()
const fileInput = ref(null)
const fileName = ref('')
const scenarioEvents = ref([])
const validConfig = ref(false)
const statusMessage = ref('Add configuration and scenario file.')
const runMessage = ref('Add valid config and at least one scenario row to continue.')
const historyLoading = ref(false)
const projectHistory = ref([])

const systemText = ref(JSON.stringify({
  nodes: [
    { node_id: 'SUP-01', node_type: 'supplier', capacity_units: 500 },
    { node_id: 'MFG-01', node_type: 'manufacturer', capacity_units: 450 },
    { node_id: 'DIST-01', node_type: 'distributor', capacity_units: 400 },
    { node_id: 'RET-01', node_type: 'retailer', capacity_units: 350 },
  ],
  skus: [
    { sku_id: 'A', unit_margin: 10, unit_weight: 1 },
    { sku_id: 'B', unit_margin: 9, unit_weight: 1 },
  ],
  lead_times: [
    { from_node: 'SUP-01', to_node: 'MFG-01', lead_time_ticks: 2 },
    { from_node: 'MFG-01', to_node: 'DIST-01', lead_time_ticks: 1 },
    { from_node: 'DIST-01', to_node: 'RET-01', lead_time_ticks: 1 },
  ],
  initial_inventory: [
    { node_id: 'SUP-01', sku_id: 'A', on_hand: 1200 },
    { node_id: 'SUP-01', sku_id: 'B', on_hand: 1200 },
    { node_id: 'MFG-01', sku_id: 'A', on_hand: 700 },
    { node_id: 'MFG-01', sku_id: 'B', on_hand: 700 },
    { node_id: 'DIST-01', sku_id: 'A', on_hand: 500 },
    { node_id: 'DIST-01', sku_id: 'B', on_hand: 500 },
    { node_id: 'RET-01', sku_id: 'A', on_hand: 300 },
    { node_id: 'RET-01', sku_id: 'B', on_hand: 300 },
  ],
}, null, 2))

const scenarioRows = computed(() => scenarioEvents.value.length)
const canStart = computed(() => validConfig.value && scenarioEvents.value.length > 0)

const pickFile = () => fileInput.value?.click()

const parseSystemConfig = () => JSON.parse(systemText.value)

const validateConfig = async () => {
  try {
    const parsed = parseSystemConfig()
    const res = await validateSystemConfig(parsed)
    const validation = res.data || {}
    validConfig.value = !!validation.valid
    statusMessage.value = validConfig.value ? 'Configuration validated.' : (validation.errors || []).join(', ')
  } catch (error) {
    validConfig.value = false
    if (error instanceof SyntaxError) {
      statusMessage.value = `Invalid JSON: ${error.message}`
    } else if (error?.response) {
      const status = error.response.status
      const detail = extractApiError(error)
      statusMessage.value = `Request failed (${status}): ${detail}`
    } else {
      statusMessage.value = extractApiError(error)
    }
  }
}

const onFile = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return
  fileName.value = file.name
  try {
    const res = await uploadScenarioFile(file)
    scenarioEvents.value = res.data?.scenario_events || []
    runMessage.value = `Loaded ${scenarioEvents.value.length} scenario rows from ${file.name}.`
  } catch (error) {
    scenarioEvents.value = []
    runMessage.value = `Upload failed: ${extractApiError(error)}`
  }
}

const startProject = async () => {
  if (!validConfig.value) {
    await validateConfig()
  }
  if (!canStart.value) {
    runMessage.value = 'Validate config and upload a non-empty scenario file to continue.'
    return
  }
  try {
    const parsed = parseSystemConfig()
    const saveRes = await saveSupplyChainProject({
      project_name: `Supply chain ${new Date().toLocaleString()}`,
      system_config: parsed,
      scenario_events: scenarioEvents.value,
      scenario_file_name: fileName.value,
    })
    const savedProjectId = saveRes.data?.project_id || ''
    const savedProjectName = saveRes.data?.project_name || 'Supply Chain Project'
    setScSession(parsed, scenarioEvents.value, fileName.value, savedProjectId, savedProjectName)
    router.push('/supply-chain/process')
  } catch (error) {
    runMessage.value = `Save failed: ${extractApiError(error)}`
  }
}

const formatDate = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString()
}

const loadHistory = async () => {
  historyLoading.value = true
  try {
    const res = await getSupplyChainProjectHistory()
    projectHistory.value = res.data?.projects || []
  } catch (error) {
    projectHistory.value = []
    statusMessage.value = `Could not load project history: ${extractApiError(error)}`
  } finally {
    historyLoading.value = false
  }
}

const openProject = async (projectId) => {
  try {
    const res = await getSupplyChainProjectById(projectId)
    const project = res.data || {}
    systemText.value = JSON.stringify(project.system_config || {}, null, 2)
    scenarioEvents.value = project.scenario_events || []
    fileName.value = project.scenario_file_name || ''
    await validateConfig()
    setScSession(
      project.system_config || {},
      project.scenario_events || [],
      project.scenario_file_name || '',
      project.project_id || '',
      project.project_name || 'Supply Chain Project'
    )
    router.push('/supply-chain/process')
  } catch (error) {
    statusMessage.value = `Could not open project: ${extractApiError(error)}`
  }
}

onMounted(loadHistory)
</script>

<style scoped>
.home-container { min-height: 100vh; background: var(--bg); font-family: 'Space Grotesk', system-ui, sans-serif; color: var(--text); }
.main-content { max-width: 1400px; margin: 0 auto; padding: 92px 40px 60px; }
.hero-section { margin-bottom: 60px; }
.hero-left { position: relative; padding-right: 520px; }
.hero-logo {
  position: absolute;
  top: 0;
  right: 0;
  width: 480px;
  max-width: 56vw;
  height: auto;
  object-fit: contain;
  border-radius: 14px;
}
.tag-row { display: flex; align-items: center; gap: 15px; margin-bottom: 25px; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }
.orange-tag { background: #ff4500; color: #fff; padding: 4px 10px; font-weight: 700; font-size: 0.75rem; }
.version-text { color: var(--muted); }
.main-title { font-size: 4.2rem; line-height: 1.2; font-weight: 500; margin: 0 0 28px; letter-spacing: -1px; }
.gradient-text { background: linear-gradient(90deg, var(--text) 0%, var(--muted) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.hero-desc { font-size: 1rem; line-height: 1.7; color: var(--muted); max-width: 760px; margin-bottom: 24px; }
.slogan-text { font-size: 1.1rem; font-weight: 520; border-left: 3px solid var(--accent); padding-left: 15px; color: var(--text); margin-bottom: 20px; }
.blinking-cursor { color: #ff4500; animation: blink 1s step-end infinite; }
@keyframes blink { 0%,100%{opacity:1;} 50%{opacity:0;} }
.decoration-square { width: 16px; height: 16px; background: #ff4500; }
.dashboard-section { display: flex; gap: 60px; border-top: 1px solid var(--border); padding-top: 50px; }
.left-panel { flex: 0.85; }
.right-panel { flex: 1.15; }
.panel-header { font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: var(--muted); display: flex; align-items: center; gap: 8px; margin-bottom: 20px; }
.status-dot { color: #ff4500; }
.section-title { font-size: 2rem; font-weight: 520; margin: 0 0 10px; }
.section-desc { color: var(--muted); margin-bottom: 20px; }
.steps-container { border: 1px solid var(--border); padding: 24px; background: var(--bg-elev); }
.steps-header { font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: var(--muted); margin-bottom: 20px; display: flex; align-items: center; gap: 8px; }
.workflow-list { display: flex; flex-direction: column; gap: 16px; }
.workflow-item { display: flex; gap: 14px; }
.step-num { font-family: 'JetBrains Mono', monospace; font-weight: 700; opacity: .35; }
.step-title { font-weight: 520; margin-bottom: 2px; }
.step-desc { font-size: 0.84rem; color: var(--muted); }
.console-box { border: 1px solid var(--border); padding: 8px; background: var(--bg-elev); }
.console-section { padding: 16px; }
.console-section.btn-section { padding-top: 0; }
.console-header { display: flex; justify-content: space-between; margin-bottom: 10px; font-family: 'JetBrains Mono', monospace; font-size: .75rem; color: var(--muted); }
.upload-zone { border: 1px dashed var(--border); height: 130px; display: flex; align-items: center; justify-content: center; cursor: pointer; background: var(--bg-soft); }
.upload-placeholder { text-align: center; }
.upload-icon { width: 36px; height: 36px; border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; margin: 0 auto 8px; color: var(--muted); }
.upload-title { font-weight: 500; font-size: .9rem; }
.console-divider { display: flex; align-items: center; margin: 8px 0; }
.console-divider::before,.console-divider::after { content:''; flex:1; height:1px; background:var(--border); }
.console-divider span { padding: 0 12px; font-family: 'JetBrains Mono', monospace; font-size: .7rem; color:var(--muted); }
.input-wrapper { border: 1px solid var(--border); background: var(--bg-soft); }
.code-input { width: 100%; border: none; background: transparent; padding: 14px; font-family: 'JetBrains Mono', monospace; font-size: .85rem; line-height: 1.5; resize: vertical; outline: none; min-height: 140px; }
.small-btn { margin-top: 10px; width: 100%; background: var(--nav-bg); color: var(--nav-text); border: 0; padding: 10px; font-family: 'JetBrains Mono', monospace; cursor: pointer; }
.start-engine-btn { width: 100%; background: var(--nav-bg); color: var(--nav-text); border: none; padding: 20px; font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 1rem; display: flex; justify-content: space-between; align-items: center; cursor: pointer; }
.start-engine-btn:disabled { background: var(--bg-soft); color:var(--muted); cursor:not-allowed; }
.cta-hint { margin: 10px 0 0; font-family: 'JetBrains Mono', monospace; font-size: .72rem; color:var(--muted); text-align: center; }
.history-section { margin-top: 38px; border-top: 1px solid var(--border); padding-top: 26px; }
.history-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.history-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.history-card { border: 1px solid var(--border); padding: 12px; background: var(--bg-elev); }
.history-title { font-weight: 700; margin-bottom: 8px; }
.history-meta { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.history-empty { font-size: 13px; color: var(--muted); }
.history-refresh { width: auto; margin-top: 0; padding: 8px 12px; }
</style>
