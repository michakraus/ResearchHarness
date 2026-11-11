<script setup lang="ts">
// The figure of the three sandboxes, on the page Sandboxes: on the left a Claude Code session,
// whose sandbox wraps each shell command and leaves git, gh, glab and ps outside; in the middle the
// two launch agents under their Seatbelt profiles, which the session reaches over MCP; on the right
// the launcher agentbox, whose one srt sandbox wraps a whole frontend and every command that it
// starts. Three columns of panels, so that no edge crosses another.
import FigArrow from './FigArrow.vue'
import FigCard from './FigCard.vue'
import FigFrame from './FigFrame.vue'
import FigPanel from './FigPanel.vue'
import { BAND, cardHeight, type Point } from './geometry'

type Box = { x: number, y: number, w: number, h: number }

const H2 = cardHeight(2)
const INNER = 16
const ROW = 64
const DASHED_TOP = 32
const GAP = 50
const TOP = BAND + INNER
const LOW = TOP + H2 + ROW
const HEIGHT = LOW + DASHED_TOP + H2 + INNER + INNER

// The left panel: a Claude Code session.
const session = { x: 0, y: 0, w: 480, h: HEIGHT }
const claude = { title: 'Claude Code', icon: 'agent', lines: ['plans and runs', 'its tool calls'], x: 110, y: TOP, w: 260, h: H2 }
const inner = { x: INNER, y: LOW, w: 230, h: DASHED_TOP + H2 + INNER }
const command = { title: 'A command', icon: 'terminal', lines: ['each one in', 'its own sandbox'], x: inner.x + 12, y: LOW + DASHED_TOP, w: inner.w - 24, h: H2 }
const outside = { title: 'git and gh', icon: 'git', lines: ['and glab and ps:', 'outside it'], x: inner.x + inner.w + 16, y: command.y, w: session.w - inner.w - 3 * INNER, h: H2 }

// The middle panel: the launch agents under their Seatbelt profiles.
const daemons = { x: session.w + GAP, y: 0, w: 240, h: HEIGHT }
const kaimon = { title: 'Kaimon server', icon: 'code', lines: ['Julia sessions', 'for the agents'], x: daemons.x + INNER, y: TOP, w: daemons.w - 2 * INNER, h: H2 }
const update = { title: 'julia-update', icon: 'install', lines: ['the nightly', 'package update'], x: daemons.x + INNER, y: command.y, w: daemons.w - 2 * INNER, h: H2 }

// The right panel: the launcher agentbox.
const box = { x: daemons.x + daemons.w + GAP, y: 0, w: 280, h: HEIGHT }
const frontend = { title: 'A frontend', icon: 'frontends', lines: ['claude, opencode,', 'omp or agy'], x: box.x + INNER, y: TOP, w: box.w - 2 * INNER, h: H2 }
const commands = { title: 'Its commands', icon: 'terminal', lines: ['and the servers', 'that it starts'], x: box.x + INNER, y: command.y, w: box.w - 2 * INNER, h: H2 }
const WIDTH = box.x + box.w

const mid = (b: Box) => b.y + b.h / 2
const cx = (b: Box) => b.x + b.w / 2
const BOX = {
  session: 'A Claude Code session', inner: 'the session sandbox', daemons: 'Seatbelt profiles', box: 'agentbox: one srt sandbox'
}
const ARROWS: { from: string, to: string, points: Point[], label?: string, labelAt?: Point }[] = [
  {
    from: claude.title, to: command.title, label: 'any other command',
    points: [[cx(command), claude.y + claude.h], [cx(command), command.y]], labelAt: [cx(command), (claude.y + claude.h + LOW) / 2]
  },
  {
    from: claude.title, to: outside.title, label: 'the four',
    points: [[cx(outside), claude.y + claude.h], [cx(outside), outside.y]], labelAt: [cx(outside), (claude.y + claude.h + LOW) / 2]
  },
  {
    from: claude.title, to: kaimon.title, label: 'MCP',
    points: [[claude.x + claude.w, mid(claude)], [kaimon.x, mid(claude)]], labelAt: [(session.w + daemons.x) / 2, mid(claude)]
  },
  {
    from: frontend.title, to: commands.title, label: 'starts',
    points: [[cx(frontend), frontend.y + frontend.h], [cx(frontend), commands.y]], labelAt: [cx(frontend), (frontend.y + frontend.h + commands.y) / 2]
  }
]
</script>

<template>
  <FigFrame
    id="fig-sandbox"
    :width="WIDTH"
    :height="HEIGHT"
    title="The sandboxes of the harness"
    desc="In a Claude Code session, Claude Code plans and runs its tool calls. Each shell command runs in its own session sandbox, except git, gh, glab and ps, which run outside it. Over MCP, the session reaches the Kaimon server, which gives the agents Julia sessions. On macOS, the Kaimon server and the julia-update job run under Seatbelt profiles of their own. The launcher agentbox starts a frontend, claude, opencode, omp or agy, inside one srt sandbox, together with its commands and the servers that it starts."
  >
    <FigPanel :box="BOX.session" :x="session.x" :y="session.y" :w="session.w" :h="session.h" :title="BOX.session" :badge="1" accent="blue">
      <FigCard v-bind="claude" accent="blue" tinted />
      <FigPanel :box="BOX.inner" :x="inner.x" :y="inner.y" :w="inner.w" :h="inner.h" :title="BOX.inner" accent="teal" dashed>
        <FigCard v-bind="command" accent="teal" />
      </FigPanel>
      <FigCard v-bind="outside" accent="amber" />
    </FigPanel>
    <FigPanel :box="BOX.daemons" :x="daemons.x" :y="daemons.y" :w="daemons.w" :h="daemons.h" :title="BOX.daemons" :badge="2" accent="violet">
      <FigCard v-bind="kaimon" accent="violet" />
      <FigCard v-bind="update" accent="violet" />
    </FigPanel>
    <FigPanel :box="BOX.box" :x="box.x" :y="box.y" :w="box.w" :h="box.h" :title="BOX.box" :badge="3" accent="teal">
      <FigCard v-bind="frontend" accent="teal" tinted />
      <FigCard v-bind="commands" accent="teal" />
    </FigPanel>
    <FigArrow v-for="a in ARROWS" :key="`${a.from} ${a.to}`" v-bind="a" />
  </FigFrame>
</template>
