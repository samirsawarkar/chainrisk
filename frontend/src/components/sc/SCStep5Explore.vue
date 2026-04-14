<template>
  <div class="workbench-panel">
    <div class="chat-shell">
      <div class="chat-log">
        <div class="chat-item" v-for="(entry, idx) in history" :key="idx" :class="entry.role">
          <div class="role">{{ entry.role === 'user' ? 'You' : 'System' }}</div>
          <div class="text" v-if="entry.role === 'user'">{{ entry.text }}</div>
          <div class="text" v-else>
            <div class="direct">{{ entry.answer?.direct_answer || entry.answer?.summary || entry.text }}</div>
            <ul v-if="(entry.answer?.evidence || []).length" class="evidence">
              <li v-for="(line, i) in entry.answer.evidence" :key="`ev-${idx}-${i}`">{{ line }}</li>
            </ul>
            <ul v-if="(entry.answer?.impact || []).length" class="impact">
              <li v-for="(line, i) in entry.answer.impact" :key="`im-${idx}-${i}`">{{ line }}</li>
            </ul>
            <div class="charts" v-if="(entry.answer?.charts || []).length">
              <BullwhipChart v-for="(chart, i) in entry.answer.charts.filter(c => c.type === 'bullwhip')" :key="`b-${idx}-${i}`" :chart="chart" />
              <CapacityChart v-for="(chart, i) in entry.answer.charts.filter(c => c.type === 'capacity')" :key="`c-${idx}-${i}`" :chart="chart" />
              <BacklogChart v-for="(chart, i) in entry.answer.charts.filter(c => c.type === 'backlog')" :key="`k-${idx}-${i}`" :chart="chart" />
            </div>
            <FlowDiagram v-if="entry.answer?.diagram" :diagram="entry.answer.diagram" />
          </div>
        </div>
      </div>
      <div class="chat-input">
        <textarea v-model="question" rows="3" placeholder="Ask about bottlenecks, failures, mitigation actions..."></textarea>
        <button class="action-btn" :disabled="loading || !question.trim()" @click="submit">Ask explore</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import BacklogChart from '../cape/BacklogChart.vue'
import BullwhipChart from '../cape/BullwhipChart.vue'
import CapacityChart from '../cape/CapacityChart.vue'
import FlowDiagram from '../cape/FlowDiagram.vue'

const emit = defineEmits(['ask'])
const props = defineProps({
  loading: Boolean,
  response: Object,
  initialHistory: {
    type: Array,
    default: () => [],
  },
})

const question = ref('')
const history = ref((props.initialHistory || []).map((row) => ({ role: row.role, text: row.text, answer: row.answer || null })))

const submit = () => {
  const q = question.value.trim()
  if (!q) return
  history.value.push({ role: 'user', text: q })
  emit('ask', q, (answer) => {
    history.value.push({
      role: 'system',
      text: answer?.summary || 'No answer returned.',
      answer: answer || null,
    })
  })
  question.value = ''
}
</script>

<style scoped>
.workbench-panel { height: 100%; background: #fafafa; padding: 24px; }
.chat-shell { height: 100%; display: flex; flex-direction: column; gap: 12px; }
.chat-log { flex: 1; overflow-y: auto; border: 1px solid #eaeaea; background: #fff; border-radius: 8px; padding: 12px; }
.chat-item { margin-bottom: 10px; font-size: 13px; }
.chat-item .role { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #777; margin-bottom: 3px; }
.chat-item.user .text { background: #f5f5f5; }
.chat-item.system .text { background: #efefef; }
.chat-item .text { border-radius: 6px; padding: 8px; line-height: 1.45; }
.direct { font-weight: 600; margin-bottom: 4px; }
.evidence { margin: 8px 0; padding-left: 16px; }
.impact { margin: 6px 0 0; padding-left: 16px; list-style: square; color: #555; font-size: 12px; }
.charts { display: grid; grid-template-columns: 1fr; gap: 8px; margin-top: 8px; }
.chat-input textarea { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 10px; font-family: 'JetBrains Mono', monospace; }
.action-btn { margin-top: 8px; width: 100%; border: 0; background: #000; color: #fff; padding: 12px; border-radius: 4px; cursor: pointer; font-family: 'JetBrains Mono', monospace; }
.action-btn:disabled { background: #ddd; color: #888; cursor: not-allowed; }
</style>
