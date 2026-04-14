import { defineStore } from 'pinia'

export const useCapeProStore = defineStore('capePro', {
  state: () => ({
    startTick: 0,
    endTick: 8,
    currentTick: 6,
    skuFilter: '',
    selectedNodeId: 'DIST-01',
    highlightTokens: [],
    /** Last POST /simulate-adjustment full `data` object (counterfactual + preview). */
    lastWhatIf: null,
  }),
  actions: {
    bootstrap(latestTick) {
      const t = Math.max(0, Number(latestTick) || 0)
      this.endTick = t
      this.currentTick = t
      this.startTick = Math.max(0, t - 8)
    },
    setRange(lo, hi) {
      const a = Math.max(0, Math.min(lo, hi))
      const b = Math.max(0, Math.max(lo, hi))
      this.startTick = a
      this.endTick = b
    },
    setCurrentTick(t) {
      this.currentTick = Math.max(0, Number(t) || 0)
    },
    setSku(s) {
      this.skuFilter = (s || '').toString().trim().toUpperCase()
    },
    setSelectedNode(id) {
      this.selectedNodeId = (id || 'DIST-01').toString()
    },
    setHighlightTokens(tokens) {
      this.highlightTokens = Array.isArray(tokens) ? tokens : []
    },
    setWhatIf(data) {
      this.lastWhatIf = data
    },
    clearWhatIf() {
      this.lastWhatIf = null
    },
  },
})
