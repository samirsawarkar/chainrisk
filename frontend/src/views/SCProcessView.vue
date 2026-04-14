<template>
  <div class="main-view">
    <header class="unified-header" aria-label="Main navigation and workflow">
      <div class="uh-row uh-primary">
        <div class="uh-brand" @click="router.push('/supply-chain')">CHAINRISK</div>
        <nav class="uh-nav" aria-label="App">
          <button type="button" class="uh-link" @click="router.push('/supply-chain')">Home</button>
          <span class="uh-link active" aria-current="page">Workflow</span>
          <button type="button" class="uh-link" @click="openVisualization">Results map</button>
          <button type="button" class="uh-link theme" @click="toggleTheme">{{ themeLabel }}</button>
        </nav>
        <span class="uh-version" title="Release tag">v1.6</span>
      </div>
      <div class="uh-row uh-workflow">
        <nav class="step-strip" aria-label="Workflow steps">
          <button
            v-for="s in stepsMeta"
            :key="s.n"
            type="button"
            class="step-pill"
            :class="{ active: currentStep === s.n, disabled: !canGoToStep(s.n) }"
            :disabled="!canGoToStep(s.n)"
            @click="goToStep(s.n)"
          >
            <span class="sn">{{ s.n }}</span><span class="sl">{{ s.label }}</span>
          </button>
        </nav>
        <button
          type="button"
          class="run-all-btn"
          :disabled="!canAutoRun || autoRunLoading || graphLoading || setupLoading || runStatus === 'running'"
          @click="runAllSteps"
        >
          {{ autoRunLoading ? 'Running…' : 'Run all steps' }}
        </button>
        <div class="layout-strip" title="Panel layout">
          <button
            v-for="mode in layoutModes"
            :key="mode.id"
            type="button"
            class="layout-btn"
            :class="{ active: viewMode === mode.id }"
            @click="viewMode = mode.id"
          >
            {{ mode.abbr }}
          </button>
        </div>
        <span class="status-indicator" :class="statusClass"><span class="dot"></span>{{ statusText }}</span>
      </div>
      <p v-if="autoRunError" class="uh-error" role="alert">{{ autoRunError }}</p>
    </header>

    <main class="content-area">
      <div class="panel-wrapper left" :style="leftPanelStyle">
        <GraphPanel :graphData="graphPanelData" :loading="graphLoading" :currentPhase="currentStep" :isSimulating="runStatus === 'running'" @refresh="buildGraphStep" @toggle-maximize="toggleMaximize('graph')" />
      </div>
      <div class="panel-wrapper right" :style="rightPanelStyle">
        <SCStep1Graph
          v-if="currentStep === 1"
          :valid="validConfig"
          :built="graphBuilt"
          :loading="graphLoading"
          :validation-message="validationMessage"
          :graph-summary="graphData?.summary"
          :system-logs="systemLogs"
          @build-graph="buildGraphStep"
          @next-step="currentStep = 2"
        />
        <SCStep2Setup
          v-else-if="currentStep === 2"
          :loading="setupLoading"
          :setup-data="setupData"
          :consistency="consistency"
          :system-logs="systemLogs"
          @build-setup="buildSetupStep"
          @next-step="currentStep = 3"
        />
        <SCStep3Run
          v-else-if="currentStep === 3"
          :running="runStatus === 'running'"
          :run-status="runStatus"
          :run-message="runMessage"
          :events="runEvents"
          :decision="decision"
          :system-logs="systemLogs"
          @run="runSimulation"
          @next-step="loadReport"
        />
        <SCStep4Report
          v-else-if="currentStep === 4"
          :report="reportData"
          @next-step="currentStep = 5"
          @open-visualization="openVisualization"
        />
        <div v-else class="step5-wrap">
          <div class="step5-tabs">
            <button type="button" class="tab" :class="{ active: step5Tab === 'chat' }" @click="step5Tab = 'chat'">Chat</button>
            <button type="button" class="tab" :class="{ active: step5Tab === 'pro' }" @click="step5Tab = 'pro'">Pro workspace</button>
          </div>
          <SCStep5Explore
            v-show="step5Tab === 'chat'"
            :loading="exploreLoading"
            :response="exploreAnswer"
            :initial-history="chatSeedHistory"
            @ask="askExplore"
          />
          <CapeProStudio v-show="step5Tab === 'pro'" />
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChainriskTheme } from '../composables/useChainriskTheme'
import GraphPanel from '../components/GraphPanel.vue'
import SCStep1Graph from '../components/sc/SCStep1Graph.vue'
import SCStep2Setup from '../components/sc/SCStep2Setup.vue'
import SCStep3Run from '../components/sc/SCStep3Run.vue'
import SCStep4Report from '../components/sc/SCStep4Report.vue'
import SCStep5Explore from '../components/sc/SCStep5Explore.vue'
import CapeProStudio from '../components/cape/CapeProStudio.vue'
import { extractApiError } from '../api/errors'
import {
  askSupplyChainExplore,
  buildSupplyChainGraph,
  checkSupplyChainConsistency,
  createSupplyChainSetup,
  getLatestDecisionSignal,
  getLatestSupplyChainReport,
  getSupplyChainProjectById,
  getSupplyChainRunStatus,
  runCapeSimulation,
  saveSupplyChainReportSnapshot,
  validateSystemConfig,
} from '../api/capeProject'
import { clearScSession, getScSession } from '../store/scSession'

const router = useRouter()
const route = useRoute()
const { themeLabel, toggleTheme } = useChainriskTheme()

const layoutModes = [
  { id: 'split', abbr: 'Split' },
  { id: 'graph', abbr: 'Graph' },
  { id: 'workbench', abbr: 'Desk' },
]

const stepsMeta = [
  { n: 1, label: 'Graph' },
  { n: 2, label: 'Setup' },
  { n: 3, label: 'Run' },
  { n: 4, label: 'Report' },
  { n: 5, label: 'Analyze' },
]

const viewMode = ref('split')
const currentStep = ref(1)
const autoRunLoading = ref(false)
const autoRunError = ref('')
const validConfig = ref(false)
const validationMessage = ref('Validating system config...')
const graphLoading = ref(false)
const setupLoading = ref(false)
const exploreLoading = ref(false)
const graphData = ref(null)
const graphBuilt = ref(false)
const setupData = ref(null)
const consistency = ref(null)
const runStatus = ref('idle')
const runMessage = ref('Ready to run.')
const runEvents = ref([])
const decision = ref(null)
const reportData = ref(null)
const exploreAnswer = ref(null)
const step5Tab = ref('chat')
const systemLogs = ref([])
const systemConfig = ref(null)
const scenarioEvents = ref([])
const runTaskId = ref(null)
const runConfig = ref({ t_max: 10 })
const projectId = ref('')
const projectName = ref('Supply Chain Project')
const chatSeedHistory = ref([])
let runPoll = null

const canAutoRun = computed(() => validConfig.value && !!systemConfig.value)

const statusClass = computed(() => {
  if (autoRunLoading.value) return 'processing'
  if (runStatus.value === 'failed') return 'error'
  if (runStatus.value === 'running') return 'processing'
  if (runStatus.value === 'completed') return 'completed'
  return 'idle'
})

const statusText = computed(() => {
  if (autoRunLoading.value) return 'Auto-run'
  if (runStatus.value === 'failed') return 'Error'
  if (runStatus.value === 'running') return 'Simulating'
  if (runStatus.value === 'completed') return 'Ready'
  return 'Ready'
})

const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, transform: 'translateX(-20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})
const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

const graphPanelData = computed(() => toGraphPanelFormat(graphData.value))

const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false })
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 120) systemLogs.value.shift()
}

function toGraphPanelFormat(capeGraph) {
  if (!capeGraph) return { nodes: [], edges: [] }
  return {
    nodes: (capeGraph.nodes || []).map((n) => ({
      uuid: n.id,
      name: n.label,
      labels: [n.type || 'node'],
      attributes: { capacity_units: n.capacity_units },
    })),
    edges: (capeGraph.edges || []).map((e) => ({
      uuid: e.id,
      source: e.source,
      target: e.target,
      name: `${e.lead_time_ticks}t lead`,
      fact: `Lead time: ${e.lead_time_ticks} ticks`,
    })),
  }
}

const toggleMaximize = (target) => {
  viewMode.value = viewMode.value === target ? 'split' : target
}

const buildGraphStep = async () => {
  graphLoading.value = true
  try {
    const res = await buildSupplyChainGraph({ system_config: systemConfig.value, scenario_events: scenarioEvents.value })
    graphData.value = res.data
    graphBuilt.value = true
    addLog('Graph built successfully.')
  } catch (error) {
    graphBuilt.value = false
    graphData.value = null
    addLog(`Graph build failed: ${extractApiError(error)}`)
  } finally {
    graphLoading.value = false
  }
}

const buildSetupStep = async () => {
  setupLoading.value = true
  try {
    const setupRes = await createSupplyChainSetup({ system_config: systemConfig.value })
    setupData.value = setupRes.data
    const payload = await checkSupplyChainConsistency({ system_config: systemConfig.value, scenario_events: scenarioEvents.value })
    consistency.value = payload.data || null
    addLog('Setup generated.')
  } catch (error) {
    setupData.value = null
    consistency.value = null
    addLog(`Setup failed: ${extractApiError(error)}`)
  } finally {
    setupLoading.value = false
  }
}

const pollRun = async () => {
  try {
    const statusRes = await getSupplyChainRunStatus(runTaskId.value)
    const statusData = statusRes.data || {}
    runStatus.value = statusData.status || 'running'
    runEvents.value = statusData.recent_events || []
    if (runStatus.value === 'completed' || runStatus.value === 'failed') {
      clearInterval(runPoll)
      runPoll = null
      if (runStatus.value === 'completed') {
        const sig = await getLatestDecisionSignal()
        decision.value = sig.data || null
        runMessage.value = 'Run complete. Decision signal generated.'
        addLog('Run completed and decision signal loaded.')
      } else {
        runMessage.value = statusData.error || 'Run failed. Check backend logs.'
        addLog(`Run failed: ${runMessage.value}`)
      }
    }
  } catch (error) {
    clearInterval(runPoll)
    runPoll = null
    runStatus.value = 'failed'
    runMessage.value = extractApiError(error)
    addLog(`Run polling error: ${runMessage.value}`)
  }
}

const runSimulation = async () => {
  try {
    runStatus.value = 'running'
    runMessage.value = 'Simulation in progress...'
    decision.value = null
    runEvents.value = []
    const runRes = await runCapeSimulation({
      project_id: projectId.value || undefined,
      system_config: systemConfig.value,
      scenario_events: scenarioEvents.value,
      config: {
        t_max: Number(runConfig.value.t_max || 10),
        sku_count: Array.isArray(systemConfig.value?.skus) ? systemConfig.value.skus.length : 1,
        supplier_count: Array.isArray(systemConfig.value?.nodes)
          ? systemConfig.value.nodes.filter((n) => String(n?.node_type || '').toLowerCase() === 'supplier').length || 1
          : 1,
      },
    })
    runTaskId.value = runRes.data?.task_id || null
    await pollRun()
    if (runStatus.value === 'running' && !runPoll) runPoll = setInterval(pollRun, 1500)
  } catch (error) {
    runStatus.value = 'failed'
    runMessage.value = extractApiError(error)
    addLog(`Run error: ${runMessage.value}`)
  }
}

const loadReport = async (opts = {}) => {
  const rethrow = opts.throwOnError === true
  try {
    const res = await getLatestSupplyChainReport()
    reportData.value = res.data || null
    if (projectId.value && reportData.value) {
      try {
        await saveSupplyChainReportSnapshot(projectId.value, reportData.value)
      } catch (e) {
        addLog(`Report snapshot save skipped: ${extractApiError(e)}`)
      }
    }
    currentStep.value = 4
  } catch (error) {
    reportData.value = null
    addLog(`Report load failed: ${extractApiError(error)}`)
    currentStep.value = 4
    if (rethrow) throw error
  }
}

const askExplore = async (question, done) => {
  exploreLoading.value = true
  try {
    const res = await askSupplyChainExplore({
      question,
      project_id: projectId.value || undefined,
      system_config: systemConfig.value,
      scenario_events: scenarioEvents.value,
      decision_signal: decision.value,
    })
    exploreAnswer.value = res.data || null
    if (done) done(res.data || {})
  } catch (error) {
    const fallback = { summary: extractApiError(error), evidence: [], causal_chain: [], decision: '', charts: [], diagram: {} }
    exploreAnswer.value = fallback
    if (done) done(fallback)
    addLog(`Explore ask failed: ${fallback.summary}`)
  } finally {
    exploreLoading.value = false
  }
}

const canGoToStep = (step) => {
  const s = Number(step)
  if (s === 1) return true
  if (s === 2) return graphBuilt.value
  if (s === 3) return graphBuilt.value && !!setupData.value && !!consistency.value?.valid
  const hasReport = !!reportData.value
  const runDone = runStatus.value === 'completed'
  if (s === 4 || s === 5) return hasReport || (graphBuilt.value && runDone)
  return false
}

const goToStep = (step) => {
  const s = Number(step)
  if (!canGoToStep(s)) return
  currentStep.value = s
}

async function waitForSimulationDone(maxMs = 20 * 60 * 1000) {
  const t0 = Date.now()
  while (Date.now() - t0 < maxMs) {
    if (runStatus.value !== 'running') {
      if (runPoll) {
        clearInterval(runPoll)
        runPoll = null
      }
      return
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  throw new Error('Simulation timed out')
}

const runAllSteps = async () => {
  autoRunError.value = ''
  if (!canAutoRun.value) {
    autoRunError.value = 'Fix configuration validation before auto-run.'
    addLog(autoRunError.value)
    return
  }
  autoRunLoading.value = true
  try {
    step5Tab.value = 'chat'
    currentStep.value = 1
    if (!graphBuilt.value) {
      await buildGraphStep()
    }
    if (!graphBuilt.value) {
      throw new Error('Graph build failed or returned no data.')
    }
    currentStep.value = 2
    await buildSetupStep()
    if (!setupData.value || !consistency.value?.valid) {
      throw new Error(consistency.value?.valid === false ? (consistency.value.errors || []).join('; ') || 'Consistency check failed.' : 'Setup did not complete.')
    }
    currentStep.value = 3
    if (runStatus.value === 'running') {
      throw new Error('A simulation is already running.')
    }
    await runSimulation()
    await waitForSimulationDone()
    if (runStatus.value !== 'completed') {
      throw new Error(runMessage.value || 'Simulation did not complete successfully.')
    }
    await loadReport({ throwOnError: true })
    if (!reportData.value) {
      throw new Error('Report did not load.')
    }
    currentStep.value = 5
    autoRunError.value = ''
    addLog('Auto-run completed: steps 1–5 finished.')
  } catch (error) {
    autoRunError.value = extractApiError(error)
    addLog(`Auto-run stopped: ${autoRunError.value}`)
  } finally {
    autoRunLoading.value = false
  }
}

const openVisualization = () => {
  const latestTick = Number(reportData.value?.tick ?? 10)
  const startTick = Math.max(0, latestTick - 9)
  router.push({
    path: '/supply-chain/visualization',
    query: { start_tick: String(startTick), end_tick: String(latestTick), project_id: projectId.value || '' },
  })
}

onMounted(async () => {
  const session = getScSession()
  const queryProjectId = String(route.query.project_id || '')
  const queryStep = Number(route.query.step || 0)

  try {
    if (session.isPending && session.systemConfig) {
      systemConfig.value = session.systemConfig
      scenarioEvents.value = session.scenarioEvents
      projectId.value = session.projectId || ''
      projectName.value = session.projectName || 'Supply Chain Project'
      clearScSession()
    } else if (queryProjectId) {
      const projectRes = await getSupplyChainProjectById(queryProjectId)
      const project = projectRes.data || {}
      systemConfig.value = project.system_config || null
      scenarioEvents.value = Array.isArray(project.scenario_events) ? project.scenario_events : []
      projectId.value = project.project_id || ''
      projectName.value = project.project_name || 'Supply Chain Project'
      reportData.value = project.latest_report || null
      chatSeedHistory.value = (project.chat_history || []).flatMap((item) => {
        const answer = item?.answer || {}
        const lines = []
        if (answer?.summary) lines.push(answer.summary)
        if (answer?.recommendation) lines.push(answer.recommendation)
        const eventLines = answer?.details?.event_lines || []
        if (eventLines.length > 0) lines.push(...eventLines)
        return [
          { role: 'user', text: item?.question || '' },
          { role: 'system', text: lines.join('\n') || 'No answer returned.', answer },
        ]
      })
    } else {
      router.push('/supply-chain')
      return
    }
    const scenarioMaxTime = Math.max(
      10,
      ...scenarioEvents.value.map((row) => Number(row?.time || 0)).filter((v) => Number.isFinite(v))
    )
    runConfig.value.t_max = scenarioMaxTime
    const res = await validateSystemConfig(systemConfig.value)
    validConfig.value = !!res.data?.valid
    validationMessage.value = validConfig.value ? 'System configuration is valid.' : (res.data?.errors || []).join(', ')
    if (queryStep >= 1 && queryStep <= 5) currentStep.value = queryStep
    addLog(`Project loaded: ${projectName.value}. Ready.`)
  } catch (error) {
    validConfig.value = false
    validationMessage.value = extractApiError(error)
    addLog(`Project init failed: ${validationMessage.value}`)
  }
})
</script>

<style scoped>
.main-view { height: 100vh; display: flex; flex-direction: column; background: var(--bg); color: var(--text); overflow: hidden; font-family: 'Space Grotesk', system-ui, sans-serif; }

.unified-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1200;
  background: var(--bg-elev);
  border-bottom: 1px solid var(--border);
  padding: 8px 14px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.uh-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; }
.uh-primary { justify-content: space-between; }
.uh-brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 16px;
  letter-spacing: 0.5px;
  cursor: pointer;
}
.uh-nav { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.uh-link {
  border: 1px solid var(--border);
  background: var(--bg-soft);
  color: var(--muted);
  padding: 5px 10px;
  font-size: 11px;
  border-radius: 4px;
  cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
}
.uh-link.active {
  background: var(--text);
  color: var(--bg-elev);
  border-color: var(--text);
  cursor: default;
}
.uh-link.theme { min-width: 52px; }
.uh-version { font-size: 10px; color: var(--muted); font-family: 'JetBrains Mono', monospace; opacity: 0.85; }
.uh-workflow { align-items: center; }
.step-strip { display: flex; flex-wrap: wrap; gap: 4px; flex: 1; min-width: 0; }
.step-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--border);
  background: var(--bg-soft);
  color: var(--muted);
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
  cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
}
.step-pill .sn { font-weight: 800; opacity: 0.7; }
.step-pill.active { background: var(--text); color: var(--bg-elev); border-color: var(--text); }
.step-pill.disabled,
.step-pill:disabled { opacity: 0.45; cursor: not-allowed; }
.run-all-btn {
  border: 1px solid var(--text);
  background: var(--text);
  color: var(--bg-elev);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}
.run-all-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.layout-strip { display: flex; gap: 2px; background: var(--bg-soft); padding: 2px; border-radius: 6px; border: 1px solid var(--border); }
.layout-btn {
  border: none;
  background: transparent;
  padding: 4px 8px;
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  border-radius: 4px;
  cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
}
.layout-btn.active { background: var(--bg-elev); color: var(--text); box-shadow: 0 1px 2px rgba(0,0,0,0.06); }
.uh-error { margin: 0; font-size: 11px; color: #b00020; font-family: 'JetBrains Mono', monospace; }

.status-indicator { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--muted); font-weight: 500; white-space: nowrap; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #9e9e9e; flex-shrink: 0; }
.status-indicator.idle .dot { background: #4caf50; }
.status-indicator.processing .dot { background: #ff9800; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4caf50; }
.status-indicator.error .dot { background: #f44336; }
@keyframes pulse { 50% { opacity: 0.5; } }

.content-area {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
  margin-top: var(--process-header-h, 118px);
  height: calc(100vh - var(--process-header-h, 118px));
  min-height: 0;
}
.panel-wrapper { height: 100%; overflow: hidden; transition: width .4s cubic-bezier(0.25,0.8,0.25,1), opacity .3s ease, transform .3s ease; will-change: width, opacity, transform; }
.panel-wrapper.left { border-right: 1px solid var(--border); }
.step5-wrap { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.step5-tabs { display: flex; gap: 4px; padding: 8px 0 10px; border-bottom: 1px solid var(--border); margin-bottom: 8px; }
.step5-tabs .tab { border: 1px solid var(--border); background: var(--bg-soft); padding: 6px 14px; font-size: 12px; font-weight: 600; border-radius: 6px; cursor: pointer; color: var(--muted); font-family: 'JetBrains Mono', monospace; }
.step5-tabs .tab.active { background: var(--text); color: var(--bg-elev); border-color: var(--text); }
</style>
