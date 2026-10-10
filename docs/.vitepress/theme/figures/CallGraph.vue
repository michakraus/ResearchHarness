<script setup lang="ts">
// One call graph of calls.data.ts: the graph of the caller `root`, or of every edge when `root`
// is empty. An agent is a blue card and a skill a yellow one.
import FigArrow from './FigArrow.vue'
import FigCard from './FigCard.vue'
import FigFrame from './FigFrame.vue'
import { data } from './calls.data'

const props = withDefaults(defineProps<{ root?: string, title: string, desc: string }>(), { root: '' })
const graph = data[props.root]
if (graph === undefined) throw new Error(`no call graph of ${props.root}`)
const id = `fig-calls-${props.root || 'all'}`
</script>

<template>
  <FigFrame :id="id" :width="graph.width" :height="graph.height" :title="props.title" :desc="props.desc">
    <FigArrow v-for="(e, i) in graph.edges" :key="i" v-bind="e" />
    <FigCard
      v-for="n in graph.nodes"
      :key="n.name"
      :x="n.x"
      :y="n.y"
      :w="n.w"
      :h="n.h"
      :icon="n.kind"
      :title="n.name"
      :lines="n.lines"
      :accent="n.kind === 'agent' ? 'blue' : 'yellow'"
      tinted
    />
  </FigFrame>
</template>
