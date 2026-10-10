<script setup lang="ts">
// A group panel at (x, y): a light body under a coloured header band with the title, and an
// optional number badge or icon in the band. `dashed` draws a group or an outcome inside a panel:
// a dashed border and a small grey title, with no band. `box` names the panel for the geometry
// check of docs:check; it is the title unless given. The slot holds what the panel groups.
import FigIcon from './FigIcon.vue'
import { BAND } from './geometry'

const props = withDefaults(defineProps<{
  x: number
  y: number
  w: number
  h: number
  title: string
  accent?: string
  badge?: number
  icon?: string
  dashed?: boolean
  box?: string
}>(), { accent: 'slate', badge: undefined, icon: undefined, dashed: false, box: undefined })

const R = 14
/** The band: the top of the panel, with its two upper corners rounded. */
const band = () => {
  const { x, y, w } = props
  return `M${x} ${y + BAND}V${y + R}Q${x} ${y} ${x + R} ${y}H${x + w - R}Q${x + w} ${y} ${x + w} ${y + R}V${y + BAND}Z`
}
const titleX = () => props.x + 16 + (props.badge !== undefined || props.icon !== undefined ? 32 : 0)
</script>

<template>
  <g :class="['fig-panel', `fig-accent-${props.accent}`, { 'fig-panel-dashed': props.dashed }]">
    <rect
      class="fig-panel-box"
      :data-box="props.box ?? props.title"
      :x="props.x"
      :y="props.y"
      :width="props.w"
      :height="props.h"
      :rx="props.dashed ? 10 : R"
    />
    <template v-if="!props.dashed">
      <path class="fig-panel-band" :d="band()" />
      <template v-if="props.badge !== undefined">
        <circle class="fig-badge" :cx="props.x + 28" :cy="props.y + BAND / 2" r="12" />
        <text class="fig-badge-text" :x="props.x + 28" :y="props.y + BAND / 2 + 4.5" font-size="13" text-anchor="middle">{{ props.badge }}</text>
      </template>
      <g v-else-if="props.icon !== undefined" :class="`fig-accent-${props.accent}`">
        <FigIcon :name="props.icon" :x="props.x + 17" :y="props.y + BAND / 2 - 10" :size="20" />
      </g>
      <text class="fig-panel-title" :x="titleX()" :y="props.y + BAND / 2 + 5" font-size="15">{{ props.title }}</text>
    </template>
    <text v-else class="fig-panel-title" :x="props.x + 14" :y="props.y + 21" font-size="12">{{ props.title }}</text>
    <slot />
  </g>
</template>
