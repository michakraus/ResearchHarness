<script setup lang="ts">
// The SVG of one figure: its size, and the title and description that a screen reader reads.
// `docs:check` finds each figure of the site by its <title>.
const props = defineProps<{
  /** A name for the ids of the title and the description, unique on the page. */
  id: string
  width: number
  height: number
  title: string
  desc: string
}>()
const pad = 12
</script>

<template>
  <svg
    class="fig"
    role="img"
    :viewBox="`${-pad} ${-pad} ${props.width + 2 * pad} ${props.height + 2 * pad}`"
    :width="props.width + 2 * pad"
    :style="{ maxWidth: `${props.width + 2 * pad}px` }"
    :aria-labelledby="`${props.id}-title ${props.id}-desc`"
  >
    <title :id="`${props.id}-title`">{{ props.title }}</title>
    <desc :id="`${props.id}-desc`">{{ props.desc }}</desc>
    <slot />
  </svg>
</template>
