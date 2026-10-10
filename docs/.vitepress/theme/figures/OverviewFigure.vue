<script setup lang="ts">
// The overview figure of the home page: the harness as the outer panel, and inside it the three
// layers of decision 5, from top to bottom: the research tree, the components and the frontends.
// Each layer's members are cards in a fixed grid.
import FigCard from './FigCard.vue'
import FigFrame from './FigFrame.vue'
import FigPanel from './FigPanel.vue'
import { BAND, cardHeight } from './geometry'

type Member = { title: string, icon: string, lines?: string[] }
type Layer = { title: string, icon: string, accent: string, columns: number, members: Member[] }

const LAYERS: Layer[] = [
  {
    title: 'The research tree', icon: 'tree', accent: 'teal', columns: 6, members: [
      { title: 'Library', icon: 'library' },
      { title: 'Knowledge', icon: 'knowledge' },
      { title: 'Packages', icon: 'package' },
      { title: 'Experiments', icon: 'experiment' },
      { title: 'Projects', icon: 'project' },
      { title: 'Papers', icon: 'paper' }
    ]
  },
  {
    title: 'The components', icon: 'components', accent: 'violet', columns: 4, members: [
      { title: 'Agents', icon: 'agent', lines: ['agents/'] },
      { title: 'Skills', icon: 'skill', lines: ['skills/'] },
      { title: 'Commands', icon: 'command', lines: ['commands/'] },
      { title: 'Rules', icon: 'rule', lines: ['rules/'] },
      { title: 'Guard hooks', icon: 'guard', lines: ['hooks/'] },
      { title: 'Git hooks and workflows', icon: 'git', lines: ['githooks/'] },
      { title: 'Scripts', icon: 'script', lines: ['scripts/'] },
      { title: 'Settings', icon: 'settings', lines: ['settings/'] }
    ]
  },
  {
    title: 'The frontends', icon: 'frontends', accent: 'blue', columns: 3, members: [
      { title: 'Claude Code', icon: 'terminal', lines: ['~/.claude/'] },
      { title: 'OpenCode', icon: 'code', lines: ['~/.config/opencode/'] },
      { title: 'oh-my-pi', icon: 'pi', lines: ['~/.omp/agent/'] }
    ]
  }
]

const WIDTH = 1080
const PAD = 20
const INNER = 16
const GAP = 12

// Stack the layers: each panel is as tall as its rows of cards.
let y = BAND + PAD
const layers = LAYERS.map((layer) => {
  const x = PAD
  const w = WIDTH - 2 * PAD
  const rows = Math.ceil(layer.members.length / layer.columns)
  const ch = cardHeight(Math.max(0, ...layer.members.map((m) => m.lines?.length ?? 0)))
  const cw = (w - 2 * INNER - (layer.columns - 1) * GAP) / layer.columns
  const h = BAND + INNER + rows * ch + (rows - 1) * GAP + INNER
  const cards = layer.members.map((m, i) => ({
    ...m,
    x: x + INNER + (i % layer.columns) * (cw + GAP),
    y: y + BAND + INNER + Math.floor(i / layer.columns) * (ch + GAP),
    w: cw,
    h: ch
  }))
  const panel = { ...layer, x, y, w, h, cards }
  y += h + PAD
  return panel
})
const HEIGHT = y
</script>

<template>
  <FigFrame
    id="fig-overview"
    :width="WIDTH"
    :height="HEIGHT"
    title="The harness and its three layers"
    desc="The harness surrounds three layers. At the top is the research tree, with the library, the knowledge, the packages, the experiments, the projects and the papers. In the middle are the components: agents, skills, commands, rules, guard hooks, git hooks and workflows, scripts and settings. At the bottom are the frontends: Claude Code, OpenCode and oh-my-pi."
  >
    <FigPanel :x="0" :y="0" :w="WIDTH" :h="HEIGHT" title="Research Harness" icon="harness" accent="slate" />
    <FigPanel
      v-for="layer in layers"
      :key="layer.title"
      :x="layer.x"
      :y="layer.y"
      :w="layer.w"
      :h="layer.h"
      :title="layer.title"
      :icon="layer.icon"
      :accent="layer.accent"
    >
      <FigCard
        v-for="card in layer.cards"
        :key="card.title"
        :x="card.x"
        :y="card.y"
        :w="card.w"
        :h="card.h"
        :icon="card.icon"
        :title="card.title"
        :lines="card.lines"
        :accent="layer.accent"
      />
    </FigPanel>
  </FigFrame>
</template>
