// The animated walk-throughs of the site, laid out at build time. A VitePress data loader: every
// build reads the sources again.
//
// Each walk-through comes from one file docs/figures/walkthrough-<name>.toml: its title, subtitle
// and steps, its boxes on a grid of cells, its dashed groups, and its edges, each with its route,
// its label and the `file:line` that states the step. A box that shows an agent or a skill takes
// its name, model and effort from sources.ts, as the call graphs do. The colour of a box says who
// acts: you and your session, an agent of each tier, a step with no agent, or an outcome.
// `harness test` checks the data files (lib/harness/docs.py); `npm run docs:check` checks the
// built figures (docs/scripts/figures.mjs).
//
// The animation is CSS in a <style> element of the figure's SVG: @keyframes fade every box but the
// active one and run a token along each edge by `offset-path`. The token takes TRAVEL seconds for
// an edge, and each step holds HOLD seconds. Under prefers-reduced-motion no animation runs, every
// box shows unfaded and no token shows.
import { readFileSync, readdirSync } from 'node:fs'
import path from 'node:path'
import { parse as parseToml } from 'smol-toml'
import { LABEL_SIZE, cardHeight, cardWidth, roundedPath, textWidth, type Point } from './geometry'
import { ROOT, claudeModels, node } from './sources'

/** The seconds that the token takes for one edge, and that each step holds. */
export const TRAVEL = 0.7
export const HOLD = 1.5
/** The opacity of a box that is not active. */
const FADED = 0.3

type Who = 'you' | 'large' | 'medium' | 'small' | 'step' | 'outcome'
/** The accent and the legend text of each colour of a box. */
const WHO: Record<Who, { accent: string, legend: string }> = {
  you: { accent: 'teal', legend: 'You and your session' },
  large: { accent: 'violet', legend: 'An agent on the large tier' },
  medium: { accent: 'blue', legend: 'An agent on the medium tier' },
  small: { accent: 'amber', legend: 'An agent on the small tier' },
  step: { accent: 'slate', legend: 'A step with no agent' },
  outcome: { accent: 'slate', legend: 'An outcome' }
}
/** The icon of a box of each kind, unless the box names one. */
const ICON = { you: 'user', skill: 'skill', agent: 'agent', step: 'workflow', outcome: 'drive' }

type Rect = { x: number, y: number, w: number, h: number }
/** A card of a walk-through: a box of the grid, or a member of a group. */
export type WalkBox = Rect & { id: string, n: number, title: string, lines: string[], icon: string, accent: string, dashed: boolean, code: boolean }
export type WalkGroup = Rect & { id: string, n: number, title: string, members: WalkBox[] }
export type WalkEdge = { n: number, from: string, to: string, points: Point[], path: string, label?: string, labelAt?: Point }
export type Walk = {
  key: string, title: string, subtitle: string, desc: string, width: number, height: number,
  boxes: WalkBox[], groups: WalkGroup[], edges: WalkEdge[],
  /** The id of the active box in each state: before the first step, then after each step. */
  states: string[],
  /** The second of the cycle at which each state starts. */
  starts: number[],
  duration: number,
  legend: { who: Who, text: string, accent: string, dashed: boolean, x: number, y: number }[],
  css: string
}

type BoxData = { id: string, cell?: [number, number], in?: string, kind: keyof typeof ICON, name?: string, shows?: string, lines?: string[], icon?: string, code?: boolean }
type GroupData = { id: string, cell: [number, number], name: string }
type EdgeData = { from: string, to: string, route: string[], label?: string, at: string, label_on?: number, label_at?: number }
type Data = { title: string, subtitle: string, steps: string[], box: BoxData[], group?: GroupData[], edge: EdgeData[] }

/** The gaps between the columns and between the rows, the top of the grid below the title, the
 * padding of a group, the height of its header, and the gap between its members. */
const GAP_X = 64
const GAP_Y = 56
const TOP = 64
const GROUP_PAD = 12
const GROUP_HEAD = 30
const GROUP_GAP = 10
const CARD = cardHeight(2)

/** The walk-through of `file`, with the name `key`. */
export function walkthrough(key: string, file: string): Walk {
  const data = parseToml(readFileSync(file, 'utf8')) as unknown as Data
  const fail = (text: string): never => { throw new Error(`${path.relative(ROOT, file)}: ${text}`) }
  const models = claudeModels()
  const groups = data.group ?? []

  // The text, the icon and the colour of each box.
  const cards = data.box.map((b, n) => {
    let title = b.name ?? b.shows ?? fail(`box ${b.id} has no name`)
    let lines = b.lines ?? []
    let who: Who
    if (b.kind === 'agent' || b.kind === 'skill') {
      const facts = node(b.shows ?? fail(`box ${b.id} shows no agent or skill`), models)
      if (facts.kind !== b.kind) fail(`box ${b.id} shows ${b.shows}, which is a ${facts.kind}`)
      title = b.name ?? facts.name
      lines = [...facts.lines]
      if (b.kind === 'skill') who = 'you'
      else if (facts.tier === 'large' || facts.tier === 'medium' || facts.tier === 'small') who = facts.tier
      else fail(`box ${b.id}: the agent ${b.shows} has no tier, so the figure cannot say who acts`)
    } else who = b.kind
    if (lines.length > 2) fail(`box ${b.id} has more than two grey lines`)
    return { data: b, n, title, lines, who, icon: b.icon ?? ICON[b.kind], code: b.code ?? false }
  })
  // One width for every card: the widest card's.
  const W = Math.max(...cards.map((c) => cardWidth(c.title, c.lines, c.code)))

  // The rows: each as high as its highest box or group, the boxes centred in it.
  const members = (g: GroupData) => cards.filter((c) => c.data.in === g.id)
  const groupHeight = (g: GroupData) => GROUP_HEAD + members(g).length * (CARD + GROUP_GAP) - GROUP_GAP + GROUP_PAD
  const cells = [...cards.filter((c) => c.data.in === undefined).map((c) => ({ cell: c.data.cell ?? fail(`box ${c.data.id} has no cell`), h: CARD })),
    ...groups.map((g) => ({ cell: g.cell, h: groupHeight(g) }))]
  const rowCount = Math.max(...cells.map((c) => c.cell[1])) + 1
  const colCount = Math.max(...cells.map((c) => c.cell[0])) + 1
  const rowH = Array.from({ length: rowCount }, (_, r) => Math.max(CARD, ...cells.filter((c) => c.cell[1] === r).map((c) => c.h)))
  const rowTop = rowH.map((_, r) => TOP + rowH.slice(0, r).reduce((s, h) => s + h + GAP_Y, 0))
  const colX = (c: number) => GROUP_PAD + c * (W + GAP_X)
  /** The x of a grid unit: a column's centre, or with .5 the centre of the gap after it. */
  const unitX = (u: number) => colX(0) + u * (W + GAP_X) + W / 2
  /** The y of a grid unit: a row's centre, or with .5 the centre of the gap below it. */
  const unitY = (v: number) => {
    const r = Math.floor(v)
    if (v === r) return rowTop[r] + rowH[r] / 2
    if (v - r !== 0.5) fail(`the grid unit ${v} is neither a row nor the gap after one`)
    return r < 0 ? rowTop[0] - GAP_Y / 2 : rowTop[r] + rowH[r] + GAP_Y / 2
  }

  const boxes: WalkBox[] = []
  const place = (c: typeof cards[number], x: number, y: number): WalkBox => ({
    id: c.data.id, n: c.n, title: c.title, lines: c.lines, icon: c.icon, code: c.code,
    accent: WHO[c.who].accent, dashed: c.who === 'outcome', x, y, w: W, h: CARD
  })
  for (const c of cards.filter((c) => c.data.in === undefined)) {
    const [col, row] = c.data.cell!
    boxes.push(place(c, colX(col), rowTop[row] + (rowH[row] - CARD) / 2))
  }
  const placedGroups: WalkGroup[] = groups.map((g, i) => {
    const h = groupHeight(g)
    const [x, y] = [colX(g.cell[0]) - GROUP_PAD, rowTop[g.cell[1]] + (rowH[g.cell[1]] - h) / 2]
    const inside = members(g).map((c, k) => place(c, x + GROUP_PAD, y + GROUP_HEAD + k * (CARD + GROUP_GAP)))
    if (inside.length === 0) fail(`the group ${g.id} has no member`)
    return { id: g.id, n: cards.length + i, title: g.name, x, y, w: W + 2 * GROUP_PAD, h, members: inside }
  })
  const byId = new Map<string, Rect>([...boxes.map((b) => [b.id, b] as const), ...placedGroups.map((g) => [g.id, g] as const)])
  for (const [i, a] of [...byId].entries()) {
    for (const b of [...byId].slice(i + 1)) {
      if (a[1].x < b[1].x + b[1].w && b[1].x < a[1].x + a[1].w && a[1].y < b[1].y + b[1].h && b[1].y < a[1].y + a[1].h) fail(`the boxes ${a[0]} and ${b[0]} overlap`)
    }
  }

  // The edges: from a side of one box, through the moves of the route, into a side of the other.
  const edges: WalkEdge[] = data.edge.map((e, n) => {
    const name = `${e.from} -> ${e.to}`
    const from = byId.get(e.from) ?? fail(`the edge ${name} starts at no box`)
    const to = byId.get(e.to) ?? fail(`the edge ${name} ends at no box`)
    if (e.route.length < 2) fail(`the edge ${name} has no route`)
    const start = /^(left|right|top|bottom)([+-]\d+)?$/.exec(e.route[0]) ?? fail(`the edge ${name} starts at ${e.route[0]}`)
    const off = Number(start[2] ?? 0)
    const side = start[1]
    let p: Point = side === 'left' ? [from.x, from.y + from.h / 2 + off] : side === 'right' ? [from.x + from.w, from.y + from.h / 2 + off]
      : side === 'top' ? [from.x + from.w / 2 + off, from.y] : [from.x + from.w / 2 + off, from.y + from.h]
    const points: Point[] = [p]
    for (const move of e.route.slice(1, -1)) {
      const m = /^([xy]) (-?\d+(?:\.5)?)([+-]\d+)?$/.exec(move) ?? fail(`the edge ${name} has the move ${move}`)
      const at = (m[1] === 'x' ? unitX(Number(m[2])) : unitY(Number(m[2]))) + Number(m[3] ?? 0)
      p = m[1] === 'x' ? [at, p[1]] : [p[0], at]
      points.push(p)
    }
    const end = e.route.at(-1)!
    const last: Point = end === 'left' ? [to.x, p[1]] : end === 'right' ? [to.x + to.w, p[1]]
      : end === 'top' ? [p[0], to.y] : end === 'bottom' ? [p[0], to.y + to.h] : fail(`the edge ${name} ends at ${end}`)
    const along = end === 'left' || end === 'right' ? [last[1], to.y, to.h] : [last[0], to.x, to.w]
    if (along[0] < along[1] + 8 || along[0] > along[1] + along[2] - 8) fail(`the edge ${name} meets the side ${end} of ${e.to} outside it`)
    points.push(last)
    for (let k = 1; k < points.length; k++) {
      const [a, b] = [points[k - 1], points[k]]
      if (a[0] !== b[0] && a[1] !== b[1]) fail(`the edge ${name} has a segment that is not horizontal or vertical`)
      if (a[0] === b[0] && a[1] === b[1]) fail(`the edge ${name} has a segment of no length`)
    }
    // The label sits on the segment `label_on`, else on the longest, at the fraction `label_at` of
    // it, else at its middle.
    const segments = points.slice(1).map((q, k) => [points[k], q] as const)
    const k = e.label_on ?? segments.map((s, i) => [Math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]), i]).sort((a, b) => b[0] - a[0])[0][1]
    const [a, b] = segments[k] ?? fail(`the edge ${name} has no segment ${k}`)
    const f = e.label_at ?? 0.5
    return {
      n, from: e.from, to: e.to, points, path: roundedPath(points),
      ...(e.label ? { label: e.label, labelAt: [a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])] as Point } : {})
    }
  })
  const edgeOf = new Map(data.edge.map((e, n) => [`${e.from} -> ${e.to}`, edges[n]]))
  const steps = data.steps.map((s) => edgeOf.get(s) ?? fail(`the step ${s} names no edge`))
  if (steps.length === 0) fail('there is no step')

  // The timing: the first box holds, then for each step the token runs along its edge, with its
  // start box active, and its end box holds.
  const duration = HOLD + steps.length * (TRAVEL + HOLD)
  const states = [steps[0].from, ...steps.map((e) => e.to)]
  const starts = [0, ...steps.map((_, k) => HOLD + k * (TRAVEL + HOLD) + TRAVEL)]
  const windows = new Map<string, [number, number][]>()
  const active = (id: string, a: number, b: number) => {
    const list = windows.get(id) ?? []
    const last = list.at(-1)
    if (last && Math.abs(last[1] - a) < 1e-9) last[1] = b
    else list.push([a, b])
    windows.set(id, list)
  }
  active(steps[0].from, 0, HOLD)
  const runs = new Map<WalkEdge, [number, number][]>()
  steps.forEach((e, k) => {
    const t = HOLD + k * (TRAVEL + HOLD)
    active(e.from, t, t + TRAVEL)
    active(e.to, t + TRAVEL, t + TRAVEL + HOLD)
    runs.set(e, [...(runs.get(e) ?? []), [t, t + TRAVEL]])
  })

  // The CSS of the animation, scoped to this figure by the class wt-<key>.
  const pct = (t: number) => `${Number(((100 * t) / duration).toFixed(4))}%`
  // A change of state takes 10 ms: the box fades and the token hides at once.
  const EPS = 0.01
  const scope = `.wt-${key}`
  const css: string[] = [
    `${scope} .wt-anim { animation-duration: ${Number(duration.toFixed(2))}s; animation-timing-function: linear; ` +
    'animation-iteration-count: infinite; animation-fill-mode: both; animation-delay: var(--wt-delay, 0s) }'
  ]
  const fade = (list: [number, number][], on: string, off: string) => {
    const stops = [`0% { ${list[0][0] === 0 ? on : off} }`]
    for (const [a, b] of list) {
      if (a > 0) stops.push(`${pct(a - EPS)} { ${off} }`, `${pct(a)} { ${on} }`)
      if (b < duration - 1e-9) stops.push(`${pct(b)} { ${on} }`, `${pct(b + EPS)} { ${off} }`)
    }
    stops.push(`100% { ${Math.abs(list.at(-1)![1] - duration) < 1e-9 ? on : off} }`)
    return stops.join(' ')
  }
  for (const [id, list] of windows) {
    const n = (byId.get(id) as WalkBox | WalkGroup).n
    css.push(`${scope} .wt-b${n} { animation-name: wt-${key}-b${n} }`, `${scope} .wt-r${n} { animation-name: wt-${key}-r${n} }`)
    css.push(`@keyframes wt-${key}-b${n} { ${fade(list, 'opacity: 1', `opacity: ${FADED}`)} }`)
    css.push(`@keyframes wt-${key}-r${n} { ${fade(list, 'opacity: 1', 'opacity: 0')} }`)
  }
  // A box that is never active stays faded while the animation runs.
  for (const b of [...boxes, ...placedGroups].filter((b) => !windows.has(b.id))) {
    css.push(`${scope} .wt-b${b.n} { opacity: ${FADED} }`)
  }
  for (const [e, list] of runs) {
    const stops = ['0% { offset-distance: 0%; opacity: 0 }']
    for (const [a, b] of list) {
      stops.push(`${pct(a - EPS)} { offset-distance: 0%; opacity: 0 }`, `${pct(a)} { offset-distance: 0%; opacity: 1 }`,
        `${pct(b)} { offset-distance: 100%; opacity: 1 }`, `${pct(b + EPS)} { offset-distance: 100%; opacity: 0 }`)
    }
    stops.push('100% { offset-distance: 100%; opacity: 0 }')
    css.push(`${scope} .wt-t${e.n} { offset-path: path('${e.path}'); animation-name: wt-${key}-t${e.n} }`)
    css.push(`@keyframes wt-${key}-t${e.n} { ${stops.join(' ')} }`)
  }
  // The controls of the page: a pause holds the animation; a step stops it and shows one state.
  css.push(
    `${scope}.wt-paused .wt-anim { animation-play-state: paused }`,
    `${scope}.wt-stepping .wt-anim { animation: none }`,
    `${scope}.wt-stepping .wt-ring.wt-on { opacity: 1 }`,
    `@media (prefers-reduced-motion: no-preference) { ${scope}.wt-stepping .wt-box { opacity: ${FADED} } ${scope}.wt-stepping .wt-box.wt-on { opacity: 1 } }`,
    `@media (prefers-reduced-motion: reduce) { ${scope} .wt-anim { animation: none } ${scope} .wt-box { opacity: 1 } ${scope} .wt-token { display: none } }`
  )

  // The legend: one entry for each colour that a box of the figure has, in the order of WHO.
  const used = new Set(cards.map((c) => c.who))
  const bottom = Math.max(...[...byId.values()].map((b) => b.y + b.h))
  const gridWidth = colX(colCount - 1) + W + GROUP_PAD
  const legend: Walk['legend'] = []
  let [lx, ly] = [0, bottom + 32]
  for (const who of Object.keys(WHO) as Who[]) {
    if (!used.has(who)) continue
    const w = 22 + textWidth(WHO[who].legend, 12) + 24
    if (lx > 0 && lx + w > gridWidth) [lx, ly] = [0, ly + 24]
    legend.push({ who, text: WHO[who].legend, accent: WHO[who].accent, dashed: who === 'outcome', x: lx, y: ly })
    lx += w
  }

  const name = (id: string) => {
    const b = [...boxes, ...placedGroups].find((x) => x.id === id)!
    return b.title
  }
  const desc = `${data.subtitle} The steps, in order: ` + steps.map((e, k) =>
    `${k + 1}. From ${name(e.from)} to ${name(e.to)}${e.label ? `: ${e.label}` : ''}.`).join(' ')
  const xs = edges.flatMap((e) => e.points.map((p) => p[0]))
  if (Math.min(...xs) < 0) fail('an edge runs left of the first column')
  return {
    key, title: data.title, subtitle: data.subtitle, desc,
    width: Math.ceil(Math.max(gridWidth, ...xs, textWidth(data.title, 18, true), textWidth(data.subtitle, 13),
      ...legend.map((l) => l.x + 22 + textWidth(l.text, 12)))),
    height: ly + 14,
    boxes: [...boxes, ...placedGroups.flatMap((g) => g.members)], groups: placedGroups, edges, states, starts, duration,
    legend, css: css.join('\n')
  }
}

declare const data: Record<string, Walk>
export { data }

const DIR = path.join(ROOT, 'docs', 'figures')

/** The walk-throughs of docs/figures/, by the name in their file name. */
export default {
  watch: ['../../../figures/walkthrough-*.toml', '../../../../agents/*.md', '../../../../skills/*/SKILL.md', '../../../../examples/models.toml'],
  load(): Record<string, Walk> {
    const result: Record<string, Walk> = {}
    for (const file of readdirSync(DIR).filter((f) => /^walkthrough-[\w-]+\.toml$/.test(f)).sort()) {
      const key = file.replace(/^walkthrough-/, '').replace(/\.toml$/, '')
      result[key] = walkthrough(key, path.join(DIR, file))
    }
    return result
  }
}
