<script setup lang="ts">
// The figure of the cycle of the edge catalogue, on the page Edges: the spec, the builder, the
// critic and the catalogue at the four corners of a square; the catalogue feeds the next spec, and
// the critic reads it too. Two parallel edges join the critic and the catalogue, one each way.
import FigArrow from './FigArrow.vue'
import FigCard from './FigCard.vue'
import FigFrame from './FigFrame.vue'
import { cardHeight, type Point } from './geometry'

type Box = { x: number, y: number, w: number, h: number }

const WIDTH = 760
const H2 = cardHeight(2)
const W = 240
const ROW = 130
const LANE = 16

const spec = { title: 'The spec', icon: 'rule', lines: ['Decided at', 'the edges'], x: 0, y: 0, w: W, h: H2 }
const builder = { title: 'The builder', icon: 'agent', lines: ['builds to', 'the spec'], x: WIDTH - W, y: 0, w: W, h: H2 }
const critic = { title: 'The critic', icon: 'verdict', lines: ['probes each', 'undecided edge'], x: WIDTH - W, y: H2 + ROW, w: W, h: H2 }
const catalogue = { title: 'Edge catalogue', icon: 'library', lines: ['one line for', 'each class'], x: 0, y: H2 + ROW, w: W, h: H2 }
const HEIGHT = catalogue.y + catalogue.h

const mid = (b: Box) => b.y + b.h / 2
const cx = (b: Box) => b.x + b.w / 2
const ARROWS: { from: string, to: string, points: Point[], label?: string, labelAt?: Point }[] = [
  {
    from: spec.title, to: builder.title, label: 'the spec bundle',
    points: [[spec.x + spec.w, mid(spec)], [builder.x, mid(spec)]], labelAt: [WIDTH / 2, mid(spec)]
  },
  {
    from: builder.title, to: critic.title, label: 'ready for critic',
    points: [[cx(builder), builder.y + builder.h], [cx(builder), critic.y]], labelAt: [cx(builder), (builder.y + builder.h + critic.y) / 2]
  },
  {
    from: critic.title, to: catalogue.title, label: 'a class found late',
    points: [[critic.x, mid(critic) - LANE], [catalogue.x + catalogue.w, mid(critic) - LANE]], labelAt: [WIDTH / 2, mid(critic) - LANE]
  },
  {
    from: catalogue.title, to: critic.title, label: 'the edges of its kind',
    points: [[catalogue.x + catalogue.w, mid(critic) + LANE], [critic.x, mid(critic) + LANE]], labelAt: [WIDTH / 2, mid(critic) + LANE]
  },
  {
    from: catalogue.title, to: spec.title, label: 'the next plan',
    points: [[cx(catalogue), catalogue.y], [cx(catalogue), spec.y + spec.h]], labelAt: [cx(catalogue), (spec.y + spec.h + catalogue.y) / 2]
  }
]
</script>

<template>
  <FigFrame
    id="fig-edges"
    :width="WIDTH"
    :height="HEIGHT"
    title="How the edge catalogue grows"
    desc="The spec decides the edges of a part. The builder gets the spec bundle and builds to the spec, and returns ready for critic. The critic probes each edge of the part's kind that the spec does not decide, from the edges of its kind in the edge catalogue. A defect of a class that the catalogue does not hold, found late, becomes a new line of the catalogue. The next plan writes its spec's Decided at the edges from the catalogue."
  >
    <FigCard v-bind="spec" accent="violet" />
    <FigCard v-bind="builder" accent="blue" tinted />
    <FigCard v-bind="critic" accent="blue" tinted />
    <FigCard v-bind="catalogue" accent="yellow" />
    <FigArrow v-for="a in ARROWS" :key="`${a.from} ${a.to}`" v-bind="a" />
  </FigFrame>
</template>
