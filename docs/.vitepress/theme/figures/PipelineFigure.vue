<script setup lang="ts">
// The figure of the pipeline from a task to a merge, on the page Challenges: a task file, the
// spec, a builder, the gates, a blind critic, a pull request and your merge, in one centre column;
// a FAIL goes back to a new builder on the left, and a class found late goes into the edge
// catalogue on the right, which the next spec reads. A fixed grid, so that no edge crosses another.
import FigArrow from './FigArrow.vue'
import FigCard from './FigCard.vue'
import FigFrame from './FigFrame.vue'
import FigPanel from './FigPanel.vue'
import { BAND, cardHeight, type Point } from './geometry'

type Card = { title: string, icon: string, lines: string[] }
type Box = { x: number, y: number, w: number, h: number }

const WIDTH = 1100
const CX = WIDTH / 2
const INNER = 16
const GAP = 12
const ROW = 56
const H2 = cardHeight(2)
const PANEL_H = BAND + INNER + H2 + INNER
const CARD_W = 260
const LOOP_X = 150

/** A card of the centre column at the height y. */
const centre = (c: Card, y: number) => ({ ...c, x: CX - CARD_W / 2, y, w: CARD_W, h: H2 })
/** A panel at (x, y) of width w with its cards side by side. */
function panel(x: number, y: number, w: number, cards: Card[]) {
  const cw = (w - 2 * INNER - (cards.length - 1) * GAP) / cards.length
  return { x, y, w, h: PANEL_H, cards: cards.map((c, i) => ({ ...c, x: x + INNER + i * (cw + GAP), y: y + BAND + INNER, w: cw, h: H2 })) }
}
const below = (b: Box) => b.y + b.h + ROW

const task = centre({ title: 'A task file', icon: 'paper', lines: ['the goal and', 'the done condition'] }, 0)
const spec = centre({ title: 'The spec', icon: 'rule', lines: ['Done when, edges,', 'named mutants'] }, below(task))
const builder = centre({ title: 'A builder', icon: 'agent', lines: ['writes the tests,', 'then the code'] }, below(spec))
const gates = panel(CX - 310, below(builder), 620, [
  { title: 'Static checks', icon: 'code', lines: ['format, NFC,', 'dispatch delta'] },
  { title: 'The tests', icon: 'check', lines: ['the affected tests,', 'the full suite'] },
  { title: 'Named mutants', icon: 'warning', lines: ['each one caught', 'by a kept test'] }
])
const critic = centre({ title: 'A blind critic', icon: 'verdict', lines: ['reads the spec and', 'the branch only'] }, below(gates))
const pr = centre({ title: 'A pull request', icon: 'pull-request', lines: ['the verifier,', 'then CI'] }, below(critic))
const merge = centre({ title: 'You merge', icon: 'user', lines: ['when the required', 'checks pass'] }, below(pr))
const catalogue = { title: 'Edge catalogue', icon: 'library', lines: ['one line for each', 'class found late'], x: WIDTH - 210, y: critic.y, w: 210, h: H2 }
const HEIGHT = merge.y + merge.h

const mid = (b: Box) => b.y + b.h / 2
const GATES = 'The gates'
const down = (from: string, to: string, a: Box, b: Box, label?: string) => {
  const [y0, y1] = [a.y + a.h, b.y]
  return { from, to, label, points: [[CX, y0], [CX, y1]] as Point[], labelAt: label ? [CX, (y0 + y1) / 2] as Point : undefined }
}
const CAT_X = catalogue.x + catalogue.w / 2
const ARROWS: { from: string, to: string, points: Point[], label?: string, labelAt?: Point }[] = [
  down(task.title, spec.title, task, spec, 'plan-parts'),
  down(spec.title, builder.title, spec, builder, 'the spec bundle'),
  down(builder.title, GATES, builder, gates, 'each round'),
  down(GATES, critic.title, gates, critic, 'all pass'),
  down(critic.title, pr.title, critic, pr, 'PASS'),
  down(pr.title, merge.title, pr, merge, 'review'),
  {
    from: critic.title, to: builder.title, label: 'FAIL',
    points: [[critic.x, mid(critic)], [LOOP_X, mid(critic)], [LOOP_X, mid(builder)], [builder.x, mid(builder)]],
    labelAt: [LOOP_X, (mid(critic) + mid(builder)) / 2]
  },
  {
    from: critic.title, to: catalogue.title, label: 'a new class',
    points: [[critic.x + critic.w, mid(critic)], [catalogue.x, mid(critic)]],
    labelAt: [(critic.x + critic.w + catalogue.x) / 2, mid(critic)]
  },
  {
    from: catalogue.title, to: spec.title, label: 'the next spec',
    points: [[CAT_X, catalogue.y], [CAT_X, mid(spec)], [spec.x + spec.w, mid(spec)]],
    labelAt: [CAT_X, (mid(spec) + catalogue.y) / 2]
  }
]
</script>

<template>
  <FigFrame
    id="fig-pipeline"
    :width="WIDTH"
    :height="HEIGHT"
    title="From a task to a merge"
    desc="A task file holds the goal and the done condition. The skill plan-parts writes the spec of each part: the Done when, the decided edges and the named mutants. A builder gets the spec bundle and writes the tests, then the code. In each round the gates run: the static checks, the tests and the named mutants. When they all pass, a blind critic reads the spec and the branch only. A FAIL goes back to a new builder. A PASS opens a pull request, which the verifier and CI check, and you merge it when the required checks pass. A defect of a new class goes into the edge catalogue, which the next spec reads."
  >
    <FigCard v-bind="task" accent="slate" />
    <FigCard v-bind="spec" accent="violet" />
    <FigCard v-bind="builder" accent="blue" tinted />
    <FigPanel :box="GATES" :x="gates.x" :y="gates.y" :w="gates.w" :h="gates.h" :title="GATES" :badge="1" accent="amber">
      <FigCard v-for="card in gates.cards" :key="card.title" v-bind="card" accent="amber" />
    </FigPanel>
    <FigCard v-bind="critic" accent="blue" tinted />
    <FigCard v-bind="pr" accent="teal" />
    <FigCard v-bind="merge" accent="blue" />
    <FigCard v-bind="catalogue" accent="yellow" />
    <FigArrow v-for="a in ARROWS" :key="`${a.from} ${a.to}`" v-bind="a" />
  </FigFrame>
</template>
