import { reactive } from 'vue'

const state = reactive({
  projectId: '',
  projectName: '',
  systemConfig: null,
  scenarioEvents: [],
  scenarioFileName: '',
  isPending: false,
})

export function setScSession(systemConfig, scenarioEvents, scenarioFileName = '', projectId = '', projectName = '') {
  state.projectId = projectId || ''
  state.projectName = projectName || ''
  state.systemConfig = systemConfig || null
  state.scenarioEvents = Array.isArray(scenarioEvents) ? scenarioEvents : []
  state.scenarioFileName = scenarioFileName || ''
  state.isPending = true
}

export function getScSession() {
  return state
}

export function clearScSession() {
  state.projectId = ''
  state.projectName = ''
  state.systemConfig = null
  state.scenarioEvents = []
  state.scenarioFileName = ''
  state.isPending = false
}
