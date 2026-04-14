<template>
  <div class="viz-page">
    <GlobalTopNav active="visualization" :project-id="projectId" />
    <header class="viz-header">
      <div class="title">CHAINRISK CAPE · Decision Visualization</div>
      <div class="controls">
        <button class="nav-btn" @click="goToReport">Report</button>
        <button class="nav-btn" @click="goToChatbot">Chatbot</button>
        <label>Start <input v-model.number="startTick" type="number" min="0" /></label>
        <label>End <input v-model.number="endTick" type="number" min="0" /></label>
        <button @click="loadAll" :disabled="loading">Refresh</button>
      </div>
    </header>
    <div v-if="errorText" class="error">{{ errorText }}</div>

    <section class="panel full">
      <h3>Bullwhip Amplification</h3>
      <img :src="imageUrls.bullwhip" alt="Bullwhip plot" />
    </section>

    <section class="grid-mid">
      <div class="panel">
        <h3>Capacity Utilization</h3>
        <img :src="imageUrls.capacity" alt="Capacity plot" />
      </div>
      <div class="panel">
        <h3>Backlog Trend</h3>
        <img :src="imageUrls.backlog" alt="Backlog plot" />
      </div>
    </section>

    <section class="grid-bottom">
      <div class="panel">
        <h3>Amplification Ratios</h3>
        <img :src="imageUrls.amplification" alt="Amplification bars" />
        <div class="table">
          <div v-for="bar in (amplification?.bars || [])" :key="bar.label" class="row">
            <span>{{ bar.label }}</span><b>{{ Number(bar.value).toFixed(3) }}</b>
          </div>
        </div>
      </div>
      <div class="panel timeline">
        <h3>Causality Timeline</h3>
        <div v-for="(item, idx) in (timeline?.timeline_items || [])" :key="idx" class="timeline-row">
          <span class="tick">T{{ item.tick }}</span>
          <span class="msg">{{ item.event_type }} · {{ item.node }} -> {{ item.target }} · {{ item.sku }} · q={{ item.quantity }}</span>
        </div>
        <div class="evidence">
          <h4>Failure Chain</h4>
          <div v-for="(line, idx) in (timeline?.root_cause_evidence || [])" :key="`ev-${idx}`">{{ line }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GlobalTopNav from '../../components/sc/GlobalTopNav.vue'
import {
  getAmplificationVisual,
  getBacklogVisual,
  getBullwhipVisual,
  getCapacityVisual,
  getTimelineVisual,
} from '../../api/capeProject'

const startTick = ref(0)
const endTick = ref(10)
const loading = ref(false)
const amplification = ref(null)
const timeline = ref(null)
const errorText = ref('')

const imageUrls = ref({
  bullwhip: '',
  capacity: '',
  backlog: '',
  amplification: '',
})
const route = useRoute()
const router = useRouter()
const objectUrls = ref([])
const projectId = ref('')

const clearObjectUrls = () => {
  for (const url of objectUrls.value) URL.revokeObjectURL(url)
  objectUrls.value = []
}

const toObjectUrl = (blob) => {
  const url = URL.createObjectURL(blob)
  objectUrls.value.push(url)
  return url
}

const fetchPngBlob = async (kind) => {
  const query = new URLSearchParams({
    format: 'png',
    start_tick: String(startTick.value),
    end_tick: String(endTick.value),
    ts: String(Date.now()),
  })
  const res = await fetch(`/api/cape/visuals/${kind}?${query.toString()}`)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${kind} PNG failed (${res.status}): ${body.slice(0, 220)}`)
  }
  return await res.blob()
}

const loadAll = async () => {
  loading.value = true
  errorText.value = ''
  try {
    const params = { start_tick: startTick.value, end_tick: endTick.value, format: 'json' }
    const [ampRes, timelineRes] = await Promise.all([
      getAmplificationVisual(params),
      getTimelineVisual(params),
    ])
    amplification.value = ampRes.data || null
    timeline.value = timelineRes.data || null
    clearObjectUrls()
    const [bullwhipPng, capacityPng, backlogPng, amplificationPng] = await Promise.all([
      fetchPngBlob('bullwhip'),
      fetchPngBlob('capacity'),
      fetchPngBlob('backlog'),
      fetchPngBlob('amplification'),
    ])
    imageUrls.value = {
      bullwhip: toObjectUrl(bullwhipPng),
      capacity: toObjectUrl(capacityPng),
      backlog: toObjectUrl(backlogPng),
      amplification: toObjectUrl(amplificationPng),
    }
  } catch (error) {
    errorText.value = error?.message || 'Visualization load failed.'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  const qs = Number(route.query.start_tick)
  const qe = Number(route.query.end_tick)
  projectId.value = String(route.query.project_id || '')
  if (Number.isFinite(qs)) startTick.value = Math.max(0, qs)
  if (Number.isFinite(qe)) endTick.value = Math.max(startTick.value, qe)
  loadAll()
})

onUnmounted(() => {
  clearObjectUrls()
})

const goToChatbot = () => {
  router.push({
    path: '/supply-chain/process',
    query: { project_id: projectId.value || '', step: '5' },
  })
}

const goToReport = () => {
  router.push({
    path: '/supply-chain/process',
    query: { project_id: projectId.value || '', step: '4' },
  })
}
</script>

<style scoped>
.viz-page { min-height: 100vh; background: var(--bg); color: var(--text); padding: 74px 18px 18px; font-family: 'Space Grotesk', system-ui, sans-serif; }
.viz-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.title { font-family: 'JetBrains Mono', monospace; font-weight: 700; }
.controls { display: flex; gap: 10px; align-items: center; }
.nav-btn { background: var(--bg-elev); border: 1px solid var(--border); color: var(--text); padding: 6px 12px; cursor: pointer; }
.controls label { font-size: 12px; color: var(--muted); display: flex; gap: 6px; align-items: center; }
.controls input { width: 70px; background: var(--bg-elev); border: 1px solid var(--border); color: var(--text); padding: 4px 6px; }
.controls button { background: var(--bg-elev); border: 1px solid var(--border); color: var(--text); padding: 6px 12px; cursor: pointer; }
.panel { background: var(--bg-elev); border: 1px solid var(--border); padding: 12px; border-radius: 8px; }
.panel h3 { margin: 0 0 8px; font-size: 14px; font-weight: 700; }
.full img { width: 100%; height: 320px; object-fit: contain; background: var(--bg-soft); border: 1px solid var(--border); }
.grid-mid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
.grid-mid img { width: 100%; height: 260px; object-fit: contain; background: var(--bg-soft); border: 1px solid var(--border); }
.grid-bottom { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
.grid-bottom img { width: 100%; height: 240px; object-fit: contain; background: var(--bg-soft); border: 1px solid var(--border); }
.table { margin-top: 10px; border-top: 1px solid var(--border); }
.row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 13px; border-bottom: 1px solid #171717; }
.timeline { max-height: 390px; overflow: auto; }
.timeline-row { font-size: 12px; display: flex; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border); }
.tick { font-family: 'JetBrains Mono', monospace; color: #ff8a65; min-width: 34px; }
.msg { color: var(--text); }
.evidence { margin-top: 10px; font-size: 12px; color: var(--muted); }
.evidence h4 { margin: 0 0 6px; color: var(--text); font-size: 12px; }
.error { margin-bottom: 10px; padding: 8px 10px; border: 1px solid #8b3a3a; background: #3a1a1a; color: #ffd0d0; border-radius: 6px; font-size: 12px; }
</style>
