<script setup lang="ts">
// One Lucide icon of icons.ts, inlined as SVG shapes at (x, y), `size` pixels wide.
import { icon } from './icons'

const props = defineProps<{ name: string, x: number, y: number, size: number }>()
const shapes = icon(props.name)
</script>

<template>
  <svg
    class="fig-icon"
    :x="props.x"
    :y="props.y"
    :width="props.size"
    :height="props.size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <component :is="tag" v-for="([tag, attrs], i) in shapes" :key="i" v-bind="attrs" />
  </svg>
</template>
