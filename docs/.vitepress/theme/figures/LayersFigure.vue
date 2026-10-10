<script setup lang="ts">
// The figure of the three layers of an installation, on the concept page: the harness, the
// profile and the tree instructions as panels on the left, each with what it holds, and arrows
// into `harness install`, which writes the configuration of the frontends. A fixed grid: the
// install card is level with the middle panel, so that the arrows of the outer panels bend in one
// lane and no edge crosses another.
import FigArrow from './FigArrow.vue'
import FigCard from './FigCard.vue'
import FigFrame from './FigFrame.vue'
import FigPanel from './FigPanel.vue'
import { BAND, cardHeight, type Point } from './geometry'

type Member = { title: string, icon: string, lines?: string[], code?: boolean }
type Layer = { box: string, title: string, icon: string, accent: string, members: Member[] }

const LAYERS: Layer[] = [
  {
    box: 'The harness', title: 'The harness · public, in this repository', icon: 'harness', accent: 'violet', members: [
      { title: 'Agents and skills', icon: 'agent', lines: ['agents/, skills/'] },
      { title: 'Rules and instructions', icon: 'rule', lines: ['rules/, instructions/'] },
      { title: 'Guard hooks', icon: 'guard', lines: ['hooks/'] },
      { title: 'Settings template', icon: 'template', lines: ['settings/'] }
    ]
  },
  {
    box: 'The profile', title: 'The profile · private, on your machine', icon: 'profile', accent: 'teal', members: [
      { title: 'profile.toml', icon: 'profile', code: true, lines: ['your paths, accounts', 'and private strings'] },
      { title: 'models.toml', icon: 'settings', code: true, lines: ['the model of each tier', 'for each frontend'] }
    ]
  },
  {
    box: 'The tree instructions', title: 'The tree instructions · private, your own directory', icon: 'tree', accent: 'yellow', members: [
      { title: 'research-tree.md', icon: 'paper', code: true, lines: ['the facts about your tree'] },
      { title: 'Your own rules and skills', icon: 'skill', lines: ['optional'] }
    ]
  }
]

const COLUMNS = 2
const PANEL_W = 600
const PAD = 20
const INNER = 16
const GAP = 12

// Stack the layers: each panel is as tall as its rows of cards.
let y = 0
const layers = LAYERS.map((layer) => {
  const rows = Math.ceil(layer.members.length / COLUMNS)
  const ch = cardHeight(Math.max(0, ...layer.members.map((m) => m.lines?.length ?? 0)))
  const cw = (PANEL_W - 2 * INNER - (COLUMNS - 1) * GAP) / COLUMNS
  const h = BAND + INNER + rows * ch + (rows - 1) * GAP + INNER
  const cards = layer.members.map((m, i) => ({
    ...m,
    x: INNER + (i % COLUMNS) * (cw + GAP),
    y: y + BAND + INNER + Math.floor(i / COLUMNS) * (ch + GAP),
    w: cw,
    h: ch
  }))
  const panel = { ...layer, x: 0, y, w: PANEL_W, h, cards }
  y += h + PAD
  return panel
})
const HEIGHT = y - PAD

const mid = (b: { y: number, h: number }) => b.y + b.h / 2
const LANE = PANEL_W + 40
const RIGHT_X = PANEL_W + 80
const RIGHT_W = 1000 - RIGHT_X
const WIDTH = RIGHT_X + RIGHT_W
const install = {
  title: 'harness install', icon: 'install', code: true, lines: ['reads the three layers and', 'writes each frontend'],
  x: RIGHT_X, y: mid(layers[1]) - cardHeight(2) / 2, w: RIGHT_W, h: cardHeight(2)
}
const frontends = {
  title: 'The frontends', icon: 'frontends', lines: ['~/.claude/, ~/.config/opencode/', '~/.omp/agent/'],
  x: RIGHT_X, y: install.y + install.h + 60, w: RIGHT_W, h: cardHeight(2)
}

const [top, middle, bottom] = layers
const right = (b: { x: number, w: number }, at: number): Point => [b.x + b.w, at]
const ARROWS: { from: string, to: string, points: Point[] }[] = [
  {
    from: top.box, to: install.title,
    points: [right(top, mid(top)), [LANE, mid(top)], [LANE, install.y + 16], [install.x, install.y + 16]]
  },
  { from: middle.box, to: install.title, points: [right(middle, mid(middle)), [install.x, mid(middle)]] },
  {
    from: bottom.box, to: install.title,
    points: [right(bottom, mid(bottom)), [LANE, mid(bottom)], [LANE, install.y + install.h - 16], [install.x, install.y + install.h - 16]]
  },
  {
    from: install.title, to: frontends.title,
    points: [[install.x + install.w / 2, install.y + install.h], [install.x + install.w / 2, frontends.y]]
  }
]
</script>

<template>
  <FigFrame
    id="fig-layers"
    :width="WIDTH"
    :height="HEIGHT"
    title="The harness, the profile and the tree instructions"
    desc="Three layers go into harness install. The harness is public and lives in this repository: the agents and skills, the rules and instructions, the guard hooks and the settings template. The profile is private and lives on your machine: profile.toml with your paths, accounts and private strings, and models.toml with the model of each tier for each frontend. The tree instructions are private and live in your own directory: research-tree.md with the facts about your tree, and optionally your own rules and skills. harness install reads the three layers and writes the configuration of each frontend into ~/.claude/, ~/.config/opencode/ and ~/.omp/agent/."
  >
    <FigPanel
      v-for="layer in layers"
      :key="layer.box"
      :box="layer.box"
      :x="layer.x"
      :y="layer.y"
      :w="layer.w"
      :h="layer.h"
      :title="layer.title"
      :icon="layer.icon"
      :accent="layer.accent"
    >
      <FigCard v-for="card in layer.cards" :key="card.title" v-bind="card" :accent="layer.accent" />
    </FigPanel>
    <FigCard v-bind="install" accent="amber" tinted />
    <FigCard v-bind="frontends" accent="blue" />
    <FigArrow v-for="a in ARROWS" :key="`${a.from} ${a.to}`" v-bind="a" />
  </FigFrame>
</template>
