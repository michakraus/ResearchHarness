<script setup lang="ts">
// A group panel at (x, y): a light body under a coloured header band with the title, and an
// optional number badge or icon in the band. `dashed` draws a group or an outcome inside a panel:
// a dashed border and a small grey title, with no band; `code` sets that title in the monospace
// font, for a command. `box` names the panel for the geometry
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
  code?: boolean
  box?: string
}>(), { accent: 'slate', badge: undefined, icon: undefined, dashed: false, code: false, box: undefined })

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
    />
    <template v-if="!props.dashed">
      <!-- The band: a rounded rectangle with the panel's corner radius, and a square one over its
           lower half, so that only its two upper corners are rounded. -->
      <rect class="fig-panel-band fig-panel-band-top" :x="props.x" :y="props.y" :width="props.w" :height="BAND" />
      <rect class="fig-panel-band" :x="props.x" :y="props.y + BAND / 2" :width="props.w" :height="BAND / 2" />
      <template v-if="props.badge !== undefined">
        <circle class="fig-badge" :cx="props.x + 28" :cy="props.y + BAND / 2" r="12" />
        <text class="fig-badge-text" :x="props.x + 28" :y="props.y + BAND / 2 + 4.5" font-size="13" text-anchor="middle">{{ props.badge }}</text>
      </template>
      <g v-else-if="props.icon !== undefined" :class="`fig-accent-${props.accent}`">
        <FigIcon :name="props.icon" :x="props.x + 17" :y="props.y + BAND / 2 - 10" :size="20" />
      </g>
      <text class="fig-panel-title" :x="titleX()" :y="props.y + BAND / 2 + 5" font-size="15">{{ props.title }}</text>
    </template>
    <text v-else :class="['fig-panel-title', { 'fig-code': props.code }]" :x="props.x + 14" :y="props.y + 21" font-size="12">{{ props.title }}</text>
    <slot />
  </g>
</template>
