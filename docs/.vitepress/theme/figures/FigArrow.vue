<script setup lang="ts">
// An arrow along the right-angled polyline `points`, from the box `from` to the box `to`, with
// rounded corners, a filled head at the last point, and an optional label centred at `labelAt`.
// The path carries the names of its two boxes, which the geometry check of docs:check reads.
import { computed } from 'vue'
import { LABEL_SIZE, roundedPath, textWidth, type Point } from './geometry'

const props = withDefaults(defineProps<{
  points: Point[]
  from: string
  to: string
  label?: string
  labelAt?: Point
}>(), { label: undefined, labelAt: undefined })

const HEAD = 8
const head = computed(() => {
  const [a, b] = props.points.slice(-2)
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1
  const [ux, uy] = [(b[0] - a[0]) / len, (b[1] - a[1]) / len]
  const base: Point = [b[0] - ux * HEAD, b[1] - uy * HEAD]
  const side = HEAD * 0.5
  return `M${b[0]} ${b[1]}L${base[0] - uy * side} ${base[1] + ux * side}L${base[0] + uy * side} ${base[1] - ux * side}Z`
})
const name = computed(() => `${props.from} → ${props.to}` + (props.label ? ` (${props.label})` : ''))
const labelBox = computed(() => {
  if (!props.label || !props.labelAt) return undefined
  const w = textWidth(props.label, LABEL_SIZE) + 10
  return { x: props.labelAt[0] - w / 2, y: props.labelAt[1] - 9, w, h: 18 }
})
</script>

<template>
  <g class="fig-arrow">
    <path
      class="fig-arrow-line"
      :data-edge="name"
      :data-from="props.from"
      :data-to="props.to"
      :d="roundedPath(props.points)"
    />
    <path class="fig-arrow-head" :d="head" />
    <template v-if="labelBox">
      <rect class="fig-arrow-label-bg" :x="labelBox.x" :y="labelBox.y" :width="labelBox.w" :height="labelBox.h" rx="5" />
      <text class="fig-arrow-label" :x="props.labelAt![0]" :y="props.labelAt![1] + 4" :font-size="LABEL_SIZE" text-anchor="middle">{{ props.label }}</text>
    </template>
  </g>
</template>
