<script setup lang="ts">
// The figure of the layers of control around one tool call, on the introduction: the
// instructions guide the agent; the agent's tool call meets the checks before the call, the
// permission settings and the guard hooks, which refuse it, ask you, or let it run; a shell
// command then runs inside the sandbox. A fixed grid with one centre column, so that no edge
// crosses another.
import FigArrow from './FigArrow.vue'
import FigCard from './FigCard.vue'
import FigFrame from './FigFrame.vue'
import FigPanel from './FigPanel.vue'
import { BAND, cardHeight, type Point } from './geometry'

type Box = { x: number, y: number, w: number, h: number }

const WIDTH = 1000
const CX = WIDTH / 2
const INNER = 16
const GAP = 12
const ROW = 60
const H2 = cardHeight(2)
const PANEL_H = BAND + INNER + H2 + INNER

/** A panel at (x, y) of width w with its cards side by side. */
function panel(x: number, y: number, w: number, cards: { title: string, icon: string, lines: string[] }[]) {
  const cw = (w - 2 * INNER - (cards.length - 1) * GAP) / cards.length
  return { x, y, w, h: PANEL_H, cards: cards.map((c, i) => ({ ...c, x: x + INNER + i * (cw + GAP), y: y + BAND + INNER, w: cw, h: H2 })) }
}

const instructions = panel(0, 0, 330, [
  { title: 'CLAUDE.md, rules, skills', icon: 'rule', lines: ['say what to do and', 'what to avoid'] }
])
const agent = { title: 'The agent', icon: 'agent', lines: ['plans its next', 'tool call'], x: CX - 110, y: PANEL_H / 2 - H2 / 2, w: 220, h: H2 }
const checks = panel(CX - 260, PANEL_H + ROW, 520, [
  { title: 'Guard hooks', icon: 'guard', lines: ['refuse an unsafe', 'shell command'] },
  { title: 'Permission settings', icon: 'settings', lines: ['deny, ask or allow', 'each tool call'] }
])
const refused = { title: 'Refused', icon: 'ban', lines: ['with a reason', 'for the agent'], x: 0, y: checks.y + PANEL_H / 2 - H2 / 2, w: 170, h: H2 }
const you = { title: 'You', icon: 'user', lines: ['answer the', 'permission prompt'], x: WIDTH - 170, y: refused.y, w: 170, h: H2 }
const sandbox = panel(CX - 190, checks.y + PANEL_H + ROW, 380, [
  { title: 'The OS sandbox', icon: 'sandbox', lines: ['limits the files and the', 'hosts of the command'] }
])
const outcome = { title: 'Your files and the network', icon: 'drive', lines: ['what the command', 'reads and writes'], x: CX - 140, y: sandbox.y + PANEL_H + ROW, w: 280, h: H2 }
const HEIGHT = outcome.y + outcome.h

const mid = (b: Box) => b.y + b.h / 2
const BOX = { instructions: 'Instructions', checks: 'Checks before the call', sandbox: 'While a shell command runs' }
const ARROWS: { from: string, to: string, points: Point[], label?: string, labelAt?: Point }[] = [
  {
    from: BOX.instructions, to: agent.title, label: 'read',
    points: [[instructions.x + instructions.w, mid(agent)], [agent.x, mid(agent)]], labelAt: [(instructions.x + instructions.w + agent.x) / 2, mid(agent)]
  },
  {
    from: agent.title, to: BOX.checks, label: 'a tool call',
    points: [[CX, agent.y + agent.h], [CX, checks.y]], labelAt: [CX, (agent.y + agent.h + checks.y) / 2]
  },
  {
    from: BOX.checks, to: refused.title, label: 'deny',
    points: [[checks.x, mid(checks)], [refused.x + refused.w, mid(checks)]], labelAt: [(checks.x + refused.x + refused.w) / 2, mid(checks)]
  },
  {
    from: BOX.checks, to: you.title, label: 'ask',
    points: [[checks.x + checks.w, mid(checks)], [you.x, mid(checks)]], labelAt: [(checks.x + checks.w + you.x) / 2, mid(checks)]
  },
  {
    from: BOX.checks, to: BOX.sandbox, label: 'allow',
    points: [[CX, checks.y + checks.h], [CX, sandbox.y]], labelAt: [CX, (checks.y + checks.h + sandbox.y) / 2]
  },
  {
    from: you.title, to: BOX.sandbox, label: 'yes',
    points: [[you.x + you.w / 2, you.y + you.h], [you.x + you.w / 2, mid(sandbox)], [sandbox.x + sandbox.w, mid(sandbox)]],
    labelAt: [you.x + you.w / 2, (you.y + you.h + mid(sandbox)) / 2]
  },
  { from: BOX.sandbox, to: outcome.title, points: [[CX, sandbox.y + sandbox.h], [CX, outcome.y]] }
]
</script>

<template>
  <FigFrame
    id="fig-control"
    :width="WIDTH"
    :height="HEIGHT"
    title="The layers of control around one tool call"
    desc="The instructions, the CLAUDE.md file, the rules and the skills, say what to do and what to avoid, and the agent reads them. The agent plans a tool call. Before the call, the guard hooks and the permission settings check it. A deny refuses the call, with a reason for the agent. An ask shows you a permission prompt, and the call runs when you answer yes. An allow lets the call run. A shell command runs inside the OS sandbox, which limits the files and the hosts that the command can reach. Then the command reads and writes your files and the network."
  >
    <FigPanel :box="BOX.instructions" :x="instructions.x" :y="instructions.y" :w="instructions.w" :h="instructions.h" title="Instructions" :badge="1" accent="violet">
      <FigCard v-for="card in instructions.cards" :key="card.title" v-bind="card" accent="violet" />
    </FigPanel>
    <FigCard v-bind="agent" accent="blue" tinted />
    <FigPanel :box="BOX.checks" :x="checks.x" :y="checks.y" :w="checks.w" :h="checks.h" :title="BOX.checks" :badge="2" accent="amber">
      <FigCard v-for="card in checks.cards" :key="card.title" v-bind="card" accent="amber" />
    </FigPanel>
    <FigCard v-bind="refused" accent="slate" />
    <FigCard v-bind="you" accent="blue" />
    <FigPanel :box="BOX.sandbox" :x="sandbox.x" :y="sandbox.y" :w="sandbox.w" :h="sandbox.h" :title="BOX.sandbox" :badge="3" accent="teal">
      <FigCard v-for="card in sandbox.cards" :key="card.title" v-bind="card" accent="teal" />
    </FigPanel>
    <FigCard v-bind="outcome" accent="slate" />
    <FigArrow v-for="a in ARROWS" :key="`${a.from} ${a.to}`" v-bind="a" />
  </FigFrame>
</template>
