import service from './index'

export const validateSystemConfig = (systemConfig) => service.post('/api/cape/validate-config', { system_config: systemConfig })

export const uploadScenarioFile = (file) => {
  const form = new FormData()
  form.append('file', file)
  return service.post('/api/cape/scenario/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const runCapeSimulation = (payload) => service.post('/api/cape/run', payload)
export const getSupplyChainRunStatus = (taskId) =>
  service.get('/api/cape/run-status', { params: taskId ? { task_id: taskId } : {} })

export const getLatestDecisionSignal = () => service.get('/api/cape/decision/latest')

export const buildSupplyChainGraph = (payload) => service.post('/api/cape/graph/build', payload)

export const createSupplyChainSetup = (payload) => service.post('/api/cape/setup/create', payload)
export const checkSupplyChainConsistency = (payload) => service.post('/api/cape/input/consistency-check', payload)

export const getLatestSupplyChainReport = () => service.get('/api/cape/report/latest')

export const askSupplyChainExplore = (payload) => service.post('/api/cape/explore/ask', payload)

export const getBullwhipVisual = (params = {}, config = {}) => service.get('/api/cape/visuals/bullwhip', { params, ...config })
export const getCapacityVisual = (params = {}, config = {}) => service.get('/api/cape/visuals/capacity', { params, ...config })
export const getBacklogVisual = (params = {}, config = {}) => service.get('/api/cape/visuals/backlog', { params, ...config })
export const getAmplificationVisual = (params = {}, config = {}) => service.get('/api/cape/visuals/amplification', { params, ...config })
export const getTimelineVisual = (params = {}, config = {}) => service.get('/api/cape/visuals/timeline', { params, ...config })

export const getBullwhipProVisual = (params = {}, config = {}) => service.get('/api/cape/visuals/bullwhip-pro', { params, ...config })
export const getCapacityHeatmapVisual = (params = {}, config = {}) => service.get('/api/cape/visuals/capacity-heatmap', { params, ...config })
export const getCapacityNodeDetail = (params = {}, config = {}) => service.get('/api/cape/visuals/node-detail', { params, ...config })
export const getFlowNetworkVisual = (params = {}, config = {}) => service.get('/api/cape/visuals/flow-network', { params, ...config })
export const getCausalityChainVisual = (params = {}, config = {}) => service.get('/api/cape/visuals/causality-chain', { params, ...config })
export const postSimulateAdjustment = (payload, config = {}) => service.post('/api/cape/simulate-adjustment', payload, config)

export const saveSupplyChainProject = (payload) => service.post('/api/cape/projects/save', payload)
export const getSupplyChainProjectHistory = () => service.get('/api/cape/projects/history')
export const getSupplyChainProjectById = (projectId) => service.get(`/api/cape/projects/${projectId}`)
export const saveSupplyChainReportSnapshot = (projectId, report) =>
  service.post(`/api/cape/projects/${projectId}/report/snapshot`, { report })
export const saveSupplyChainChatMessage = (projectId, question, answer) =>
  service.post(`/api/cape/projects/${projectId}/chat`, { question, answer })
