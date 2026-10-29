<script setup lang="ts">
// The flow figure of the home page: the inputs on the left, `harness install`, the one install
// path of every frontend, in the middle, and the frontends on the right, with OpenCode, oh-my-pi
// and Antigravity above Claude Code. A fixed grid: the private inputs are above the sources, so
// that no edge crosses another.
import FigArrow from './FigArrow.vue'
import FigCard from './FigCard.vue'
import FigFrame from './FigFrame.vue'
import FigPanel from './FigPanel.vue'
import { BAND, cardHeight, type Point } from './geometry'

type Box = { x: number, y: number, w: number, h: number }
type Card = Box & { title: string, icon: string, lines?: string[], code?: boolean }

const WIDTH = 1080
const GAP = 70
const COLUMNS = [
  { title: 'Inputs', badge: 1, accent: 'violet', w: 330 },
  { title: 'Install', badge: 2, accent: 'amber', w: 310 },
  { title: 'Frontends', badge: 3, accent: 'blue', w: 300 }
]
const columns = COLUMNS.map((c, i) => ({ ...c, x: COLUMNS.slice(0, i).reduce((s, d) => s + d.w + GAP, 0) }))
const INNER = 16
const GROUP_TOP = 30
const STEP = 10

/** The cards of a dashed group at (x, y), stacked; the group's box and its cards. */
function group(x: number, y: number, w: number, members: Omit<Card, keyof Box>[]) {
  let top = y + GROUP_TOP
  const cards = members.map((m) => {
    const h = cardHeight(m.lines?.length ?? 0)
    const card = { ...m, x: x + 12, y: top, w: w - 24, h }
    top += h + STEP
    return card
  })
  return { x, y, w, h: top - STEP + 12 - y, cards }
}

const c1 = columns[0]
const privateGroup = group(c1.x + INNER, BAND + INNER, c1.w - 2 * INNER, [
  { title: 'Profile and model tables', icon: 'profile', lines: ['~/.config/research-harness/'] },
  { title: 'Tree instructions', icon: 'tree' }
])
const sourceGroup = group(c1.x + INNER, privateGroup.y + privateGroup.h + INNER, c1.w - 2 * INNER, [
  { title: 'Agents, skills, rules', icon: 'sources', lines: ['commands, instructions'] },
  { title: 'Guard hooks', icon: 'guard', lines: ['hooks/'] },
  { title: 'Adapters of the frontends', icon: 'adapter', lines: ['adapters/'] },
  { title: 'Settings template', icon: 'template', lines: ['settings/'] }
])

const mid = (b: Box) => b.y + b.h / 2
const c2 = columns[1]
const c3 = columns[2]
// harness install is a dashed group with a card for each of its steps, in the order in which
// lib/harness/install.py runs them: cmd_install reads the profile and the model tables, plans each
// frontend in the order of FRONTENDS (Claude Code, OpenCode, oh-my-pi, Antigravity), installs the
// Julia environment, syncs the Python environment, and writes the files of each plan. The Claude
// Code plan starts with the merge of ~/.claude/settings.json (`files = [settings]` in `plan`,
// adapters/claude/adapter.py) and ends with the stamp.
const installGroup = group(c2.x + INNER, BAND + INNER, c2.w - 2 * INNER, [
  { title: 'Read the profile', icon: 'profile', lines: ['and the model tables'] },
  { title: 'Render the sources', icon: 'sources', lines: ['a plan for each frontend'] },
  { title: 'Install Julia packages', icon: 'package', lines: ['for the Julia scripts'] },
  { title: 'Sync Python environment', icon: 'package', lines: ['from uv.lock, with uv'] },
  { title: 'Merge the settings', icon: 'settings-install', lines: ['into ~/.claude/settings.json'] },
  { title: 'Write Claude Code', icon: 'install', lines: ['the files of ~/.claude/'] },
  { title: 'Write the stamp', icon: 'drive', lines: ['of the Claude Code layer'] },
  { title: 'Write the other layers', icon: 'install', lines: ['OpenCode, oh-my-pi, Antigravity'] }
])
const HEIGHT = Math.max(sourceGroup.y + sourceGroup.h, installGroup.y + installGroup.h) + INNER
const frontend = (title: string, icon: string, line: string, y: number, h = cardHeight(1)): Card =>
  ({ title, icon, lines: [line], x: c3.x + INNER, y, w: c3.w - 2 * INNER, h })
const opencode = frontend('OpenCode', 'code', '~/.config/opencode/', BAND + 2 * INNER)
const omp = frontend('oh-my-pi', 'pi', '~/.omp/agent/', opencode.y + opencode.h + 2 * INNER)
const antigravity = frontend('Antigravity', 'frontends', '~/.gemini/config/', omp.y + omp.h + 2 * INNER)
// Claude Code is level with the steps that write its files, from the settings to the stamp.
const claude = frontend('Claude Code', 'terminal', '~/.claude/', installGroup.cards[4].y, cardHeight(2))

// The arrows: each leaves its box on the right and enters the next on the left.
const right = (b: Box, y: number): Point => [b.x + b.w, y]
const left = (b: Box, y: number): Point => [b.x, y]
const ARROWS = [
  {
    from: 'Private, on your machine', to: 'harness install',
    points: [right(privateGroup, mid(privateGroup)), left(installGroup, mid(privateGroup))]
  },
  {
    from: 'The sources, in this repository', to: 'harness install',
    points: [right(sourceGroup, sourceGroup.y + 40), left(installGroup, sourceGroup.y + 40)]
  },
  { from: 'harness install', to: 'OpenCode', points: [right(installGroup, mid(opencode)), left(opencode, mid(opencode))] },
  { from: 'harness install', to: 'oh-my-pi', points: [right(installGroup, mid(omp)), left(omp, mid(omp))] },
  { from: 'harness install', to: 'Antigravity', points: [right(installGroup, mid(antigravity)), left(antigravity, mid(antigravity))] },
  { from: 'harness install', to: 'Claude Code', points: [right(installGroup, mid(claude)), left(claude, mid(claude))] }
] as { from: string, to: string, points: Point[], label?: string, labelAt?: Point }[]
</script>

<template>
  <FigFrame
    id="fig-flow"
    :width="WIDTH"
    :height="HEIGHT"
    title="From the sources to the frontends"
    desc="The sources of this repository, the agents, skills, rules, commands and instructions, the guard hooks, the settings template and the adapters, and two private inputs, the profile with the model tables and the tree instructions, go into harness install. Its steps, in order: it reads the profile and the model tables, renders the sources into a plan for each frontend, installs the Julia packages for the Julia scripts, syncs the Python environment from uv.lock with uv, merges the settings template into ~/.claude/settings.json, writes the files of Claude Code into ~/.claude/ and then the stamp of that layer, and writes the files of OpenCode into ~/.config/opencode/, those of oh-my-pi into ~/.omp/agent/ and those of Antigravity into ~/.gemini/config/. harness install is the one install path of every frontend."
  >
    <FigPanel
      v-for="c in columns"
      :key="c.title"
      :x="c.x"
      :y="0"
      :w="c.w"
      :h="HEIGHT"
      :title="c.title"
      :badge="c.badge"
      :accent="c.accent"
    />
    <FigPanel :x="privateGroup.x" :y="privateGroup.y" :w="privateGroup.w" :h="privateGroup.h" title="Private, on your machine" dashed>
      <FigCard v-for="card in privateGroup.cards" :key="card.title" v-bind="card" accent="teal" />
    </FigPanel>
    <FigPanel :x="sourceGroup.x" :y="sourceGroup.y" :w="sourceGroup.w" :h="sourceGroup.h" title="The sources, in this repository" dashed>
      <FigCard v-for="card in sourceGroup.cards" :key="card.title" v-bind="card" accent="violet" />
    </FigPanel>
    <FigPanel :x="installGroup.x" :y="installGroup.y" :w="installGroup.w" :h="installGroup.h" title="harness install" dashed code>
      <FigCard v-for="card in installGroup.cards" :key="card.title" v-bind="card" accent="amber" />
    </FigPanel>
    <FigCard v-for="card in [opencode, omp, antigravity, claude]" :key="card.title" v-bind="card" accent="blue" />
    <FigArrow v-for="a in ARROWS" :key="`${a.from} ${a.to}`" v-bind="a" />
  </FigFrame>
</template>
