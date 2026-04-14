<template>
  <nav class="global-top-nav">
    <div class="brand" @click="router.push('/supply-chain')">CHAINRISK</div>
    <div class="links">
      <button class="nav-btn" :class="{ active: active === 'landing' }" @click="router.push('/supply-chain')">Landing</button>
      <button class="nav-btn" :class="{ active: active === 'process' }" @click="openProcess">Process</button>
      <button class="nav-btn" :class="{ active: active === 'visualization' }" @click="openVisualization">Visualization</button>
      <button class="nav-btn theme-btn" @click="toggleTheme">{{ themeLabel }}</button>
    </div>
  </nav>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useChainriskTheme } from '../../composables/useChainriskTheme'

const props = defineProps({
  active: {
    type: String,
    default: 'landing',
  },
  projectId: {
    type: String,
    default: '',
  },
})

const router = useRouter()
const { themeLabel, toggleTheme } = useChainriskTheme()

const openProcess = () => {
  if (props.projectId) {
    router.push({ path: '/supply-chain/process', query: { project_id: props.projectId } })
    return
  }
  router.push('/supply-chain/process')
}

const openVisualization = () => {
  if (props.projectId) {
    router.push({ path: '/supply-chain/visualization', query: { project_id: props.projectId } })
    return
  }
  router.push('/supply-chain/visualization')
}

</script>

<style scoped>
.global-top-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 52px;
  background: var(--bg-elev);
  color: var(--text);
  border-bottom: 1px solid var(--border);
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
}
.brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 15px;
  letter-spacing: 0.6px;
  cursor: pointer;
}
.links {
  display: flex;
  align-items: center;
  gap: 6px;
}
.nav-btn {
  border: 1px solid var(--border);
  background: var(--bg-soft);
  color: var(--muted);
  padding: 5px 9px;
  font-size: 11px;
  border-radius: 3px;
  cursor: pointer;
}
.nav-btn.active {
  background: var(--bg);
  color: var(--text);
  border-color: color-mix(in srgb, var(--border) 75%, var(--text) 25%);
}
.theme-btn {
  min-width: 54px;
}
</style>
