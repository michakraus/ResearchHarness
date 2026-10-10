<script setup lang="ts">
// One animated walk-through of walkthroughs.data.ts, by the name of its data file
// docs/figures/walkthrough-<name>.toml. The build renders the SVG and its <style>, so the
// animation plays with JavaScript off. With JavaScript on, the play, pause and step controls show
// below it: a pause holds the animation, and a step stops it and shows the next state, with its
// box active.
import { computed, h, onMounted, ref } from 'vue'
import FigArrow from './FigArrow.vue'
import FigCard from './FigCard.vue'
import FigFrame from './FigFrame.vue'
import FigPanel from './FigPanel.vue'
import { data } from './walkthroughs.data'

const props = defineProps<{ name: string }>()
const wt = data[props.name]
if (wt === undefined) throw new Error(`no walk-through ${props.name} in docs/figures/`)

// The <style> of the animation, inside the SVG. A template drops a <style> tag, a render function
// does not.
const AnimationStyle = () => h('style', { innerHTML: wt.css })

const top = new Set(wt.groups.flatMap((g) => g.members.map((m) => m.id)))
const boxes = wt.boxes.filter((b) => !top.has(b.id))
const rings = [...boxes, ...wt.groups]

const root = ref<HTMLElement>()
const live = ref(false)
onMounted(() => { live.value = true })
const paused = ref(false)
/** The state that the step control shows, or -1 while the animation runs. */
const state = ref(-1)
/** The start of the animation, in seconds into the cycle: a play after a step goes on from there. */
const delay = ref(0)
const on = (id: string) => state.value >= 0 && wt.states[state.value] === id

/** The state that the running animation shows: the last state that starts before its time. */
function current(): number {
  const animation = root.value?.querySelector('.wt-anim')?.getAnimations?.()[0]
  const progress = animation?.effect?.getComputedTiming().progress
  if (progress == null) return 0
  const t = progress * wt.duration
  return wt.starts.reduce((s, start, i) => (start <= t ? i : s), 0)
}
function play() {
  if (state.value >= 0) {
    delay.value = -wt.starts[state.value]
    state.value = -1
  }
  paused.value = false
}
function pause() {
  paused.value = true
}
function step() {
  const s = state.value >= 0 ? state.value : current()
  state.value = (s + 1) % wt.states.length
  paused.value = true
}
const svgClass = computed(() => ['wt', `wt-${wt.key}`, { 'wt-paused': paused.value, 'wt-stepping': state.value >= 0 }])
const svgStyle = computed(() => ({ '--wt-delay': `${delay.value}s` }))
</script>

<template>
  <div ref="root" class="wt-figure">
    <FigFrame :id="`fig-wt-${wt.key}`" :width="wt.width" :height="wt.height" :title="wt.title" :desc="wt.desc" :class="svgClass" :style="svgStyle">
      <AnimationStyle />
      <text class="wt-title" x="0" y="18" font-size="18">{{ wt.title }}</text>
      <text class="fig-muted" x="0" y="40" font-size="13">{{ wt.subtitle }}</text>
      <FigArrow v-for="e in wt.edges" :key="`e${e.n}`" :from="e.from" :to="e.to" :points="e.points" :label="e.label" :label-at="e.labelAt" />
      <g v-for="g in wt.groups" :key="g.id" :class="['wt-box', 'wt-anim', `wt-b${g.n}`, { 'wt-on': on(g.id) }]">
        <FigPanel :box="g.id" :x="g.x" :y="g.y" :w="g.w" :h="g.h" :title="g.title" dashed>
          <FigCard
            v-for="m in g.members"
            :key="m.id"
            :box="m.id"
            :x="m.x"
            :y="m.y"
            :w="m.w"
            :h="m.h"
            :icon="m.icon"
            :title="m.title"
            :lines="m.lines"
            :accent="m.accent"
            :code="m.code"
            :tinted="!m.dashed"
            :dashed="m.dashed"
          />
        </FigPanel>
      </g>
      <g v-for="b in boxes" :key="b.id" :class="['wt-box', 'wt-anim', `wt-b${b.n}`, { 'wt-on': on(b.id) }]">
        <FigCard
          :box="b.id"
          :x="b.x"
          :y="b.y"
          :w="b.w"
          :h="b.h"
          :icon="b.icon"
          :title="b.title"
          :lines="b.lines"
          :accent="b.accent"
          :code="b.code"
          :tinted="!b.dashed"
          :dashed="b.dashed"
        />
      </g>
      <rect
        v-for="r in rings"
        :key="`r${r.n}`"
        :class="['wt-ring', 'wt-anim', `wt-r${r.n}`, { 'wt-on': on(r.id) }]"
        :x="r.x"
        :y="r.y"
        :width="r.w"
        :height="r.h"
      />
      <circle v-for="e in wt.edges" :key="`t${e.n}`" :class="['wt-token', 'wt-anim', `wt-t${e.n}`]" r="6" />
      <g v-for="l in wt.legend" :key="l.who" :class="`fig-accent-${l.accent}`">
        <rect :class="['wt-swatch', { 'wt-swatch-dashed': l.dashed }]" :x="l.x" :y="l.y - 10" width="16" height="12" />
        <text class="fig-muted" :x="l.x + 22" :y="l.y" font-size="12">{{ l.text }}</text>
      </g>
    </FigFrame>
    <div v-if="live" class="wt-controls" role="group" :aria-label="`Controls of the animation: ${wt.title}`">
      <button type="button" :aria-pressed="!paused && state < 0" @click="play">Play</button>
      <button type="button" :aria-pressed="paused && state < 0" @click="pause">Pause</button>
      <button type="button" :aria-pressed="state >= 0" @click="step">Step</button>
    </div>
  </div>
</template>
