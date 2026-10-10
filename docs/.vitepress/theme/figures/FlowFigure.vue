<script setup lang="ts">
// The flow figure of the home page: the inputs on the left, `harness install` and
// `harness settings install` in the middle, and the frontends on the right, with OpenCode and
// oh-my-pi above Claude Code. A fixed grid: the private inputs are above the sources, and the
// settings template is the last source, so that no edge crosses another.
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
  { title: 'Install', badge: 2, accent: 'amber', w: 300 },
  { title: 'Frontends', badge: 3, accent: 'blue', w: 310 }
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
const HEIGHT = sourceGroup.y + sourceGroup.h + INNER
const template = sourceGroup.cards[3]

const mid = (b: Box) => b.y + b.h / 2
const c2 = columns[1]
const c3 = columns[2]
const install: Card = {
  title: 'harness install', icon: 'install', code: true, lines: ['writes the configuration', 'of each frontend'],
  x: c2.x + INNER, y: 0, w: c2.w - 2 * INNER, h: cardHeight(2)
}
const settings: Card = {
  title: 'harness settings install', icon: 'settings-install', code: true, lines: ['writes the permission', 'and sandbox settings'],
  x: c2.x + INNER, y: mid(template) - cardHeight(2) / 2, w: c2.w - 2 * INNER, h: cardHeight(2)
}
const frontend = (title: string, icon: string, line: string, y: number, h = cardHeight(1)): Card =>
  ({ title, icon, lines: [line], x: c3.x + INNER, y, w: c3.w - 2 * INNER, h })
const opencode = frontend('OpenCode', 'code', '~/.config/opencode/', BAND + 3 * INNER)
const omp = frontend('oh-my-pi', 'pi', '~/.omp/agent/', opencode.y + opencode.h + 3 * INNER)
// harness install sits level with oh-my-pi, and Claude Code level with harness settings install,
// so that it takes the arrows of both.
install.y = mid(omp) - install.h / 2
const claude = frontend('Claude Code', 'terminal', '~/.claude/', settings.y, settings.h)

// The arrows: each leaves its box on the right and enters the next on the left.
const right = (b: Box, y: number): Point => [b.x + b.w, y]
const left = (b: Box, y: number): Point => [b.x, y]
const lane1 = c1.x + c1.w + GAP / 2
const lane2 = c2.x + c2.w + GAP / 2
const ARROWS = [
  {
    from: 'Private, on your machine', to: 'harness install',
    points: [right(privateGroup, mid(privateGroup)), [lane1, mid(privateGroup)], [lane1, install.y + 16], left(install, install.y + 16)]
  },
  {
    from: 'The sources, in this repository', to: 'harness install',
    points: [right(sourceGroup, install.y + install.h - 16), left(install, install.y + install.h - 16)]
  },
  { from: 'Settings template', to: 'harness settings install', points: [right(template, mid(template)), left(settings, mid(template))] },
  {
    from: 'harness install', to: 'OpenCode',
    points: [right(install, install.y + 16), [lane2, install.y + 16], [lane2, mid(opencode)], left(opencode, mid(opencode))]
  },
  { from: 'harness install', to: 'oh-my-pi', points: [right(install, mid(omp)), left(omp, mid(omp))] },
  {
    from: 'harness install', to: 'Claude Code',
    points: [right(install, install.y + install.h - 16), [lane2, install.y + install.h - 16], [lane2, claude.y + 16], left(claude, claude.y + 16)]
  },
  {
    from: 'harness settings install', to: 'Claude Code', label: 'settings.json',
    points: [right(settings, claude.y + claude.h - 20), left(claude, claude.y + claude.h - 20)], labelAt: [lane2, claude.y + claude.h - 20]
  }
] as { from: string, to: string, points: Point[], label?: string, labelAt?: Point }[]
</script>

<template>
  <FigFrame
    id="fig-flow"
    :width="WIDTH"
    :height="HEIGHT"
    title="From the sources to the frontends"
    desc="The sources of this repository, the agents, skills, rules, commands and instructions, the guard hooks, the settings template and the adapters, and two private inputs, the profile with the model tables and the tree instructions, go into harness install. It writes the configuration of Claude Code into ~/.claude/, of OpenCode into ~/.config/opencode/ and of oh-my-pi into ~/.omp/agent/. The settings template also goes into harness settings install, which writes ~/.claude/settings.json for Claude Code."
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
    <FigCard v-bind="install" accent="amber" tinted />
    <FigCard v-bind="settings" accent="amber" tinted />
    <FigCard v-for="card in [opencode, omp, claude]" :key="card.title" v-bind="card" accent="blue" />
    <FigArrow v-for="a in ARROWS" :key="`${a.from} ${a.to}`" v-bind="a" />
  </FigFrame>
</template>
