<template>
  <div class="fn-wrap">
    <div class="fn-head">
      <span class="title">Flow network</span>
      <label class="tick">Tick <input type="number" :value="modelTick" min="0" @change="onTickInput" /></label>
    </div>
    <svg ref="svgEl" class="svg" viewBox="0 0 520 220" />
    <div v-if="selected" class="side">
      <div class="side-title">{{ selected.id }}</div>
      <div>demand {{ selected.demand }}</div>
      <div>order {{ selected.order }}</div>
      <div>backlog {{ selected.backlog }}</div>
    </div>
  </div>
</template>

<script setup>
import * as d3 from 'd3'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  flow: { type: Object, default: null },
  modelTick: { type: Number, default: 0 },
  highlightTokens: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:tick', 'select-node'])

const svgEl = ref(null)
const selected = ref(null)

function onTickInput(ev) {
  const v = Math.max(0, parseInt(ev.target.value, 10) || 0)
  emit('update:tick', v)
}

function layoutPx(layout, id) {
  const L = layout?.[id]
  if (!L) return { x: 80, y: 80 }
  return { x: 80 + L.x * 180, y: 40 + L.y * 140 }
}

function draw() {
  const svg = d3.select(svgEl.value)
  if (!svg.node()) return
  svg.selectAll('*').remove()
  const f = props.flow
  if (!f?.nodes?.length) {
    svg.append('text').attr('x', 160).attr('y', 100).attr('font-size', 12).text('No flow data')
    return
  }
  const layout = f.layout || {}
  const hl = (props.highlightTokens || []).map((t) => String(t).toUpperCase())

  const g = svg.append('g')
  const links = g
    .append('g')
    .attr('fill', 'none')
    .attr('stroke', '#999')
    .attr('stroke-width', 2)
    .selectAll('path')
    .data(f.edges || [])
    .join('path')
    .attr('d', (d) => {
      const a = layoutPx(layout, d.from)
      const b = layoutPx(layout, d.to)
      return `M${a.x},${a.y}L${b.x},${b.y}`
    })
    .attr('opacity', (d) => {
      const hit = hl.some((h) => d.from.toUpperCase().includes(h) || d.to.toUpperCase().includes(h))
      return hl.length ? (hit ? 1 : 0.25) : 1
    })
    .style('cursor', 'pointer')
    .on('click', (ev, d) => {
      ev.stopPropagation()
      emit('select-node', { type: 'edge', edge: d })
    })

  links.append('title').text((d) => `${d.from}→${d.to}: flow ${d.value}, amp ${d.amp?.toFixed?.(2) ?? d.amp}×`)

  const nodeG = g
    .append('g')
    .selectAll('g')
    .data(f.nodes)
    .join('g')
    .attr('transform', (d) => {
      const p = layoutPx(layout, d.id)
      return `translate(${p.x - 52},${p.y - 28})`
    })
    .style('cursor', 'pointer')
    .on('click', (ev, d) => {
      ev.stopPropagation()
      selected.value = d
      emit('select-node', { type: 'node', node: d })
    })

  nodeG
    .append('rect')
    .attr('width', 104)
    .attr('height', 56)
    .attr('rx', 6)
    .attr('fill', (d) => {
      const hit = hl.some((h) => d.id.toUpperCase().includes(h) || (d.role || '').toUpperCase().includes(h))
      if (hl.length && !hit) return '#f0f0f0'
      return '#e3f2fd'
    })
    .attr('stroke', '#1976d2')

  nodeG
    .append('text')
    .attr('x', 52)
    .attr('y', 14)
    .attr('text-anchor', 'middle')
    .attr('font-size', 11)
    .attr('font-weight', 700)
    .text((d) => d.id)

  nodeG
    .append('text')
    .attr('x', 52)
    .attr('y', 30)
    .attr('text-anchor', 'middle')
    .attr('font-size', 9)
    .attr('fill', '#444')
    .text((d) => `d ${d.demand} · o ${d.order}`)

  nodeG
    .append('text')
    .attr('x', 52)
    .attr('y', 44)
    .attr('text-anchor', 'middle')
    .attr('font-size', 9)
    .attr('fill', '#666')
    .text((d) => `bl ${d.backlog}`)

  g.append('g')
    .selectAll('text.edge-lbl')
    .data(f.edges || [])
    .join('text')
    .attr('font-size', 9)
    .attr('fill', '#555')
    .attr('text-anchor', 'middle')
    .attr('x', (d) => {
      const a = layoutPx(layout, d.from)
      const b = layoutPx(layout, d.to)
      return (a.x + b.x) / 2
    })
    .attr('y', (d) => {
      const a = layoutPx(layout, d.from)
      const b = layoutPx(layout, d.to)
      return (a.y + b.y) / 2 - 6
    })
    .text((d) => `${d.amp?.toFixed?.(2) ?? d.amp}×`)
}

watch(
  () => [props.flow, props.highlightTokens],
  () => draw(),
  { deep: true }
)

onMounted(() => {
  draw()
})

onBeforeUnmount(() => {
  selected.value = null
})
</script>

<style scoped>
.fn-wrap {
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 8px;
  background: var(--bg-elev, #fff);
  padding: 8px;
  display: grid;
  grid-template-columns: 1fr 120px;
  gap: 8px;
}
.fn-head {
  grid-column: 1 / -1;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title {
  font-weight: 700;
  font-size: 12px;
}
.tick input {
  width: 56px;
  margin-left: 6px;
  font-family: inherit;
}
.svg {
  width: 100%;
  height: auto;
  min-height: 200px;
  background: #fafafa;
  border-radius: 6px;
}
.side {
  font-size: 10px;
  border-left: 1px solid #eee;
  padding-left: 8px;
}
.side-title {
  font-weight: 700;
  margin-bottom: 6px;
}
</style>
