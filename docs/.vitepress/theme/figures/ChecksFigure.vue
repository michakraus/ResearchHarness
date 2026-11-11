<script setup lang="ts">
// The figure of the checks between an edit and a merge, on the page Tests and CI: the pre-commit
// hook on every commit, the part's gate on every build round, CI on the pull request, and your
// merge. One centre column of panels, so that no edge crosses another.
import FigArrow from './FigArrow.vue'
import FigCard from './FigCard.vue'
import FigFrame from './FigFrame.vue'
import FigPanel from './FigPanel.vue'
import { BAND, cardHeight, type Point } from './geometry'

type Card = { title: string, icon: string, lines: string[] }

const WIDTH = 1000
const CX = WIDTH / 2
const INNER = 16
const GAP = 12
const ROW = 56
const H2 = cardHeight(2)
const PANEL_H = BAND + INNER + H2 + INNER

/** A panel at (x, y) of width w with its cards side by side. */
function panel(x: number, y: number, w: number, cards: Card[]) {
  const cw = (w - 2 * INNER - (cards.length - 1) * GAP) / cards.length
  return { x, y, w, h: PANEL_H, cards: cards.map((c, i) => ({ ...c, x: x + INNER + i * (cw + GAP), y: y + BAND + INNER, w: cw, h: H2 })) }
}

const edit = { title: 'An edit', icon: 'edit', lines: ['the agent changes', 'a source file'], x: CX - 130, y: 0, w: 260, h: H2 }
const commit = panel(0, edit.y + edit.h + ROW, WIDTH, [
  { title: 'Test layout', icon: 'tree', lines: ['each test file', 'in its group'] },
  { title: 'Format', icon: 'code', lines: ['JuliaFormatter,', 'the repository style'] },
  { title: 'Unicode NFC', icon: 'script', lines: ['normal form C', 'in every source'] },
  { title: 'Package load', icon: 'package', lines: ['using, in a', 'fresh process'] }
])
const gate = panel(0, commit.y + PANEL_H + ROW, WIDTH, [
  { title: 'Affected tests', icon: 'check', lines: ['the test files', 'the diff reaches'] },
  { title: 'Named mutants', icon: 'warning', lines: ['each one caught', 'by a kept test'] },
  { title: 'Dispatch delta', icon: 'verdict', lines: ['new ambiguities,', 'piracies, fields'] },
  { title: 'Full suite', icon: 'agent', lines: ['julia-test-runner,', 'beside the critic'] }
])
const ci = panel(CX - 380, gate.y + PANEL_H + ROW, 760, [
  { title: 'Tests', icon: 'workflow', lines: ['oldest and latest', 'Julia, three systems'] },
  { title: 'Downgrade', icon: 'workflow', lines: ['the lowest', 'compat bounds'] },
  { title: 'Doctests', icon: 'workflow', lines: ['the examples', 'of the manual'] }
])
const merge = { title: 'You merge', icon: 'pull-request', lines: ['when the required', 'checks pass'], x: CX - 130, y: ci.y + PANEL_H + ROW, w: 260, h: H2 }
const HEIGHT = merge.y + merge.h

const BOX = {
  commit: 'Every commit: the pre-commit hook',
  gate: 'Every build round: the part\'s gate',
  ci: 'Every push of the branch: CI'
}
const down = (from: string, to: string, y0: number, y1: number, label?: string) => ({
  from, to, label, points: [[CX, y0], [CX, y1]] as Point[], labelAt: label ? [CX, (y0 + y1) / 2] as Point : undefined
})
const ARROWS = [
  down(edit.title, BOX.commit, edit.y + edit.h, commit.y, 'git commit'),
  down(BOX.commit, BOX.gate, commit.y + PANEL_H, gate.y, 'each round'),
  down(BOX.gate, BOX.ci, gate.y + PANEL_H, ci.y, 'git push'),
  down(BOX.ci, merge.title, ci.y + PANEL_H, merge.y, 'all green')
]
</script>

<template>
  <FigFrame
    id="fig-checks"
    :width="WIDTH"
    :height="HEIGHT"
    title="The checks between an edit and a merge"
    desc="An edit of a source file meets three groups of checks before you merge it. On every commit, the pre-commit hook checks the test layout, the format with JuliaFormatter, the Unicode normal form and that the package loads. In every build round, the part's gate runs the affected tests, the named mutants and the dispatch delta, and julia-test-runner runs the full suite beside the critic. On every push of the branch, CI runs the tests on the oldest and the latest Julia on three systems, the downgrade job with the lowest compat bounds, and the doctests. You merge when the required checks pass."
  >
    <FigCard v-bind="edit" accent="blue" tinted />
    <FigPanel :box="BOX.commit" :x="commit.x" :y="commit.y" :w="commit.w" :h="commit.h" :title="BOX.commit" :badge="1" accent="violet">
      <FigCard v-for="card in commit.cards" :key="card.title" v-bind="card" accent="violet" />
    </FigPanel>
    <FigPanel :box="BOX.gate" :x="gate.x" :y="gate.y" :w="gate.w" :h="gate.h" :title="BOX.gate" :badge="2" accent="amber">
      <FigCard v-for="card in gate.cards" :key="card.title" v-bind="card" accent="amber" />
    </FigPanel>
    <FigPanel :box="BOX.ci" :x="ci.x" :y="ci.y" :w="ci.w" :h="ci.h" :title="BOX.ci" :badge="3" accent="teal">
      <FigCard v-for="card in ci.cards" :key="card.title" v-bind="card" accent="teal" />
    </FigPanel>
    <FigCard v-bind="merge" accent="blue" tinted />
    <FigArrow v-for="a in ARROWS" :key="`${a.from} ${a.to}`" v-bind="a" />
  </FigFrame>
</template>
