<template>
  <div class="cx">
    <div class="cx-head">
      <span class="title">Causality trace</span>
      <span v-if="payload?.nearest_tick_note" class="note">{{ payload.nearest_tick_note }}</span>
    </div>
    <ol class="steps">
      <li
        v-for="(line, idx) in payload?.lines || []"
        :key="idx"
        :class="{ active: activeIdx === idx }"
        @click="onStep(idx, line)"
      >
        {{ line }}
      </li>
    </ol>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  payload: { type: Object, default: null },
})

const emit = defineEmits(['highlight'])

const activeIdx = ref(-1)

function onStep(idx, line) {
  activeIdx.value = idx
  const tokens = []
  const u = (line || '').toUpperCase()
  ;['RET', 'DIST', 'MFG', 'SUP'].forEach((role) => {
    if (u.includes(role)) tokens.push(role)
  })
  emit('highlight', tokens)
}

watch(
  () => props.payload,
  () => {
    activeIdx.value = -1
  }
)
</script>

<style scoped>
.cx {
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 8px;
  background: var(--bg-elev, #fff);
  padding: 8px;
}
.cx-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}
.title {
  font-weight: 700;
  font-size: 12px;
}
.note {
  font-size: 10px;
  color: #b45309;
}
.steps {
  margin: 0;
  padding-left: 18px;
  font-size: 11px;
  line-height: 1.5;
}
.steps li {
  cursor: pointer;
  padding: 4px 2px;
  border-radius: 4px;
}
.steps li:hover {
  background: #f5f5f5;
}
.steps li.active {
  background: #e3f2fd;
}
</style>
