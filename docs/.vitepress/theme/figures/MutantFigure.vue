<script setup lang="ts">
// The figure of one mutant, on the page Mutant testing: a source line, the mutant, the tests on a
// copy, and the two outcomes, caught and survived; a survivor is closed with a test or a reason.
// A fixed grid, so that no edge crosses another.
import FigArrow from './FigArrow.vue'
import FigCard from './FigCard.vue'
import FigFrame from './FigFrame.vue'
import { cardHeight, type Point } from './geometry'

type Box = { x: number, y: number, w: number, h: number }

const WIDTH = 1000
const H2 = cardHeight(2)
const ROW = 64
const W = 260

const source = { title: 'A source line', icon: 'code', lines: ['clamp(f, 0.2, 5.0)', 'in src/step.jl'], x: 0, y: 0, w: W, h: H2 }
const mutant = { title: 'A mutant', icon: 'edit', lines: ['max(f, 0.2): the', 'upper bound gone'], x: 370, y: 0, w: W, h: H2 }
const tests = { title: 'The tests', icon: 'check', lines: ['run on a copy', 'of the package'], x: WIDTH - W, y: 0, w: W, h: H2 }
const caught = { title: 'Caught', icon: 'verdict', lines: ['a test sees', 'the change'], x: 370, y: H2 + ROW, w: W, h: H2 }
const survived = { title: 'Survived', icon: 'warning', lines: ['no test sees', 'the change'], x: WIDTH - 200, y: H2 + ROW, w: 200, h: H2 }
const close = { title: 'Close it', icon: 'check', lines: ['a new test,', 'or a reason'], x: WIDTH - 200, y: survived.y + H2 + ROW, w: 200, h: H2 }
const HEIGHT = close.y + close.h

const mid = (b: Box) => b.y + b.h / 2
const right = (a: Box, b: Box, label: string) => ({
  from: '', to: '', label, points: [[a.x + a.w, mid(a)], [b.x, mid(a)]] as Point[], labelAt: [(a.x + a.w + b.x) / 2, mid(a)] as Point
})
const CAUGHT_X = tests.x + 20
const SURVIVED_X = survived.x + survived.w / 2
const ARROWS: { from: string, to: string, points: Point[], label?: string, labelAt?: Point }[] = [
  { ...right(source, mutant, 'change one line'), from: source.title, to: mutant.title },
  { ...right(mutant, tests, 'run the units'), from: mutant.title, to: tests.title },
  {
    from: tests.title, to: caught.title, label: 'a test fails',
    points: [[CAUGHT_X, tests.y + tests.h], [CAUGHT_X, mid(caught)], [caught.x + caught.w, mid(caught)]],
    labelAt: [CAUGHT_X, (tests.y + tests.h + mid(caught)) / 2]
  },
  {
    from: tests.title, to: survived.title, label: 'all pass',
    points: [[SURVIVED_X, tests.y + tests.h], [SURVIVED_X, survived.y]], labelAt: [SURVIVED_X, (tests.y + tests.h + survived.y) / 2]
  },
  {
    from: survived.title, to: close.title, label: 'the builder',
    points: [[SURVIVED_X, survived.y + survived.h], [SURVIVED_X, close.y]], labelAt: [SURVIVED_X, (survived.y + survived.h + close.y) / 2]
  }
]
</script>

<template>
  <FigFrame
    id="fig-mutant"
    :width="WIDTH"
    :height="HEIGHT"
    title="From a source line to a closed survivor"
    desc="A source line, such as clamp(f, 0.2, 5.0) in src/step.jl, becomes a mutant: one changed line, here max(f, 0.2), with the upper bound gone. The tests run on a copy of the package. When a test fails, the mutant is caught: a test sees the change. When every test passes, the mutant survives: no test sees the change. The builder closes a survivor with a new test that catches it, or with a reason why the change does not matter."
  >
    <FigCard v-bind="source" accent="slate" />
    <FigCard v-bind="mutant" accent="amber" tinted />
    <FigCard v-bind="tests" accent="blue" />
    <FigCard v-bind="caught" accent="teal" dashed />
    <FigCard v-bind="survived" accent="amber" dashed />
    <FigCard v-bind="close" accent="blue" tinted />
    <FigArrow v-for="a in ARROWS" :key="`${a.from} ${a.to}`" v-bind="a" />
  </FigFrame>
</template>
