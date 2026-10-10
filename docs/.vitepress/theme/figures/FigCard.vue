<script setup lang="ts">
// A card: a rounded box at (x, y) with an icon on a tinted square, a title and up to two grey
// lines. `tinted` fills the box with the accent's light colour; `dashed` draws an outcome, with a
// dashed border and no shadow. `box` names the card for the geometry check of docs:check; it is
// the title unless given.
import { computed } from 'vue'
import FigIcon from './FigIcon.vue'
import { CARD_PAD, ICON_BOX, LINE_SIZE, TITLE_SIZE, cardWidth } from './geometry'

const props = withDefaults(defineProps<{
  x: number
  y: number
  w: number
  h: number
  icon: string
  title: string
  lines?: string[]
  accent?: string
  tinted?: boolean
  dashed?: boolean
  code?: boolean
  box?: string
}>(), { lines: () => [], accent: 'slate', tinted: false, dashed: false, code: false, box: undefined })

// A hand layout that gives a card too little room stops the build.
const need = cardWidth(props.title, props.lines, props.code)
if (need > props.w) throw new Error(`the card "${props.title}" needs ${need} px and has ${props.w}`)

const LINE = 15
const TITLE = 17
const text = computed(() => {
  const lines = props.lines.slice(0, 2)
  const top = props.y + (props.h - (TITLE + LINE * lines.length)) / 2
  return {
    title: top + 13,
    lines: lines.map((line, i) => ({ line, y: top + TITLE + LINE * i + 11.5 }))
  }
})
</script>

<template>
  <g :class="['fig-card', `fig-accent-${props.accent}`, { 'fig-card-tinted': props.tinted, 'fig-card-dashed': props.dashed }]">
    <rect
      class="fig-card-box"
      :data-box="props.box ?? props.title"
      :x="props.x"
      :y="props.y"
      :width="props.w"
      :height="props.h"
    />
    <rect
      class="fig-icon-bg"
      :x="props.x + CARD_PAD"
      :y="props.y + (props.h - ICON_BOX) / 2"
      :width="ICON_BOX"
      :height="ICON_BOX"
    />
    <FigIcon :name="props.icon" :x="props.x + CARD_PAD + 7" :y="props.y + (props.h - ICON_BOX) / 2 + 7" :size="ICON_BOX - 14" />
    <text
      :class="{ 'fig-code': props.code }"
      :x="props.x + 2 * CARD_PAD + ICON_BOX"
      :y="text.title"
      :font-size="TITLE_SIZE"
      font-weight="600"
    >{{ props.title }}</text>
    <text
      v-for="l in text.lines"
      :key="l.line"
      class="fig-muted"
      :x="props.x + 2 * CARD_PAD + ICON_BOX"
      :y="l.y"
      :font-size="LINE_SIZE"
    >{{ l.line }}</text>
  </g>
</template>
