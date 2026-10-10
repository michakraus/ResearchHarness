// The call graphs of docs/src/agents-at-work.md, laid out at build time. A VitePress data loader:
// every build reads the sources again, so a figure changes when a source changes.
//
// The edges come from docs/figures/calls.toml: one entry for each spawn. The kind of each node
// comes from where its source is, its effort from the source's frontmatter, and an agent's model
// from its tier and the [claude] table of examples/models.toml. elkjs lays out each graph (layered,
// with orthogonal edges), and the CallGraph component draws it. `harness test` checks calls.toml.
import { readFileSync, existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import ELK from 'elkjs/lib/elk.bundled.js'
import { parse as parseToml } from 'smol-toml'
import { parse as parseYaml } from 'yaml'
import { LABEL_SIZE, cardHeight, cardWidth, textWidth, type Point } from './geometry'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..')

type Call = { caller: string, callee: string, at: string, effort?: string, label?: string }

/** A node of a laid-out graph: a card. */
export type GraphNode = { name: string, kind: 'agent' | 'skill', lines: string[], x: number, y: number, w: number, h: number }
/** An edge of a laid-out graph: its polyline and its label. */
export type GraphEdge = { from: string, to: string, label?: string, points: Point[], labelAt?: Point }
export type Graph = { width: number, height: number, nodes: GraphNode[], edges: GraphEdge[] }

/** The frontmatter of the Markdown file `file`, read as YAML. */
function frontmatter(file: string) {
  const m = /^---\n([\s\S]*?)\n---\n/.exec(readFileSync(file, 'utf8'))
  if (!m) throw new Error(`${file} has no frontmatter`)
  return parseYaml(m[1])
}

/** The name, kind and the two grey lines (model, effort) of the agent or skill `name`. */
function node(name: string, models: Record<string, string>) {
  const agent = path.join(ROOT, 'agents', `${name}.md`)
  const kind = existsSync(agent) ? 'agent' : 'skill'
  const meta = frontmatter(kind === 'agent' ? agent : path.join(ROOT, 'skills', name, 'SKILL.md'))
  let model: string
  // A skill runs in the session that loads it, on the session's model, whatever its `model:`.
  if (kind === 'skill') model = "the session's model"
  else if (meta.model === undefined) model = "the caller's model"
  else if (models[meta.model] === undefined) throw new Error(`${name}: no model for the tier ${meta.model}`)
  else model = models[meta.model]
  const effort = meta.effort ?? "the session's effort"
  return { name, kind, lines: [`${kind} on ${model}`, `effort: ${effort}`] } as const
}

/** The entries of `calls` that `root` reaches: its own spawns, then their callees' spawns. */
function reached(calls: Call[], root?: string) {
  if (root === undefined) return calls
  const seen = new Set([root])
  const frontier = [root]
  while (frontier.length > 0) {
    const caller = frontier.shift()
    for (const c of calls) {
      if (c.caller === caller && !seen.has(c.callee)) {
        seen.add(c.callee)
        frontier.push(c.callee)
      }
    }
  }
  return calls.filter((c) => seen.has(c.caller))
}

const LAYOUT = {
  'elk.algorithm': 'layered',
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.layered.spacing.nodeNodeBetweenLayers': '44',
  'elk.layered.spacing.edgeNodeBetweenLayers': '20',
  'elk.layered.spacing.edgeEdgeBetweenLayers': '14',
  'elk.spacing.nodeNode': '26',
  'elk.spacing.edgeNode': '20',
  'elk.spacing.edgeEdge': '14',
  'elk.spacing.edgeLabel': '6',
  'elk.edgeLabels.inline': 'true',
  'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
  'elk.layered.thoroughness': '100',
  'elk.layered.crossingMinimization.greedySwitch.type': 'TWO_SIDED',
  'elk.padding': '[top=0,left=0,bottom=0,right=0]'
}

type Direction = 'RIGHT' | 'DOWN'
// The options of each direction. The parts of a graph that share no node are laid out as one
// graph, so that their layers line up. Downwards, the rows come from `rows` as partitions, the
// simple node placement packs each row, and the edges from one box leave it on one trunk.
const OPTIONS: Record<Direction, Record<string, string>> = {
  RIGHT: { 'elk.direction': 'RIGHT', 'elk.separateConnectedComponents': 'false' },
  DOWN: {
    'elk.direction': 'DOWN',
    'elk.separateConnectedComponents': 'false',
    'elk.partitioning.activate': 'true',
    'elk.layered.nodePlacement.strategy': 'SIMPLE',
    'elk.layered.mergeEdges': 'true',
    'elk.spacing.nodeNode': '16',
    'elk.spacing.edgeNode': '12',
    'elk.spacing.edgeEdge': '10'
  }
}
/** The most boxes in one row of a graph that runs downwards: three cards fit the doc column. */
const ROW = 3

/** The rows of a graph that runs downwards: a node's depth is the longest path to it from a node
 * that nothing calls. The nodes of one depth fill rows of at most ROW boxes, in the order of
 * `names`, with the nodes that call others last, so that they are next to their callees. */
function rows(names: string[], edges: Call[]): Map<string, number> {
  const depth = new Map(names.map((n) => [n, 0]))
  for (let changed = true, rounds = 0; changed; rounds++) {
    if (rounds > names.length) throw new Error(`the calls of ${names.join(', ')} have a cycle`)
    changed = false
    for (const e of edges) {
      if (depth.get(e.callee)! < depth.get(e.caller)! + 1) {
        depth.set(e.callee, depth.get(e.caller)! + 1)
        changed = true
      }
    }
  }
  const calls = (n: string) => edges.some((e) => e.caller === n)
  const result = new Map<string, number>()
  let row = 0
  for (const d of [...new Set(depth.values())].sort((a, b) => a - b)) {
    const group = names.filter((n) => depth.get(n) === d).sort((a, b) => Number(calls(a)) - Number(calls(b)))
    for (let i = 0; i < group.length; i += ROW) {
      for (const n of group.slice(i, i + ROW)) result.set(n, row)
      row++
    }
  }
  return result
}

// The doc column (688 px) draws a figure of at most 765 px, its frame's padding of 12 px on each
// side included, at a scale of 0.9 or more.
const MAX_WIDTH = 765 - 2 * 12

const round = (n: number) => Math.round(n * 2) / 2

/** The laid-out call graph of `root`, or of every edge when `root` is undefined. */
export async function callGraph(root?: string): Promise<Graph> {
  const calls: Call[] = parseToml(readFileSync(path.join(ROOT, 'docs', 'figures', 'calls.toml'), 'utf8')).call as Call[]
  const models = parseToml(readFileSync(path.join(ROOT, 'examples', 'models.toml'), 'utf8')).claude as Record<string, string>
  if (root !== undefined && !calls.some((c) => c.caller === root)) throw new Error(`calls.toml has no edge from ${root}`)
  const edges = reached(calls, root)
  const names = [...new Set(edges.flatMap((c) => [c.caller, c.callee]))]
  const nodes = names.map((name) => node(name, models))
  const labels = edges.map((c) => [c.label, c.effort && `at ${c.effort} effort`].filter(Boolean).join(', '))
  const elk = new ELK()
  const row = rows(names, edges)
  /** The layout of the graph in `direction`, each node as wide as `widths` says. */
  const lay = (direction: Direction, widths: Map<string, number>) => elk.layout({
    id: 'root',
    layoutOptions: { ...LAYOUT, ...OPTIONS[direction] },
    children: nodes.map((n) => ({
      id: n.name, width: widths.get(n.name)!, height: cardHeight(2),
      ...(direction === 'DOWN' ? { layoutOptions: { 'elk.partitioning.partition': String(row.get(n.name)) } } : {})
    })),
    edges: edges.map((e, i) => ({
      id: `e${i}`,
      sources: [e.caller],
      targets: [e.callee],
      labels: labels[i] ? [{ text: labels[i], width: textWidth(labels[i], LABEL_SIZE) + 10, height: 18 }] : []
    }))
  })
  /** The layers of a layout: the names of the nodes in each column or row. A layer is a set of
   * nodes whose extents along the direction overlap, as the check of the built site reads it. */
  const layersOf = (g: Awaited<ReturnType<typeof lay>>, direction: Direction) => {
    const [start, size] = direction === 'RIGHT' ? ['x', 'width'] as const : ['y', 'height'] as const
    const layers: { end: number, names: string[] }[] = []
    for (const c of [...g.children!].sort((a, b) => a[start]! - b[start]!)) {
      const last = layers.at(-1)
      if (last && c[start]! < last.end) {
        last.names.push(c.id)
        last.end = Math.max(last.end, c[start]! + c[size]!)
      } else layers.push({ end: c[start]! + c[size]!, names: [c.id] })
    }
    return layers.map((l) => l.names.sort())
  }
  /** The layout in `direction` with the boxes of each layer as wide as the widest box of the
   * layer: a first layout gives the layers, and a second one lays out the wider boxes. */
  const aligned = async (direction: Direction) => {
    const natural = new Map(nodes.map((n) => [n.name, cardWidth(n.name, [...n.lines])]))
    const first = layersOf(await lay(direction, natural), direction)
    const widths = new Map(first.flatMap((layer) => {
      const w = Math.max(...layer.map((name) => natural.get(name)!))
      return layer.map((name) => [name, w] as const)
    }))
    const g = await lay(direction, widths)
    const second = layersOf(g, direction)
    if (JSON.stringify(second) !== JSON.stringify(first)) {
      throw new Error(`the call graph of ${root ?? 'every edge'} changes its layers when its boxes widen: ${JSON.stringify(first)}, ${JSON.stringify(second)}`)
    }
    return g
  }
  // A graph runs to the right when it fits the doc column so, and downwards when it fits only so.
  // When neither fits, it runs to the right, and the check of the built site names it.
  let direction: Direction = 'RIGHT'
  let graph = await aligned(direction)
  if (graph.width! > MAX_WIDTH) {
    const down = await aligned('DOWN')
    if (down.width! <= MAX_WIDTH) [graph, direction] = [down, 'DOWN']
  }
  const placed = new Map(graph.children!.map((c) => [c.id, c]))
  return {
    width: round(graph.width!),
    height: round(graph.height!),
    nodes: nodes.map((n) => {
      const c = placed.get(n.name)!
      return { name: n.name, kind: n.kind, lines: [...n.lines], x: round(c.x!), y: round(c.y!), w: c.width!, h: c.height! }
    }),
    edges: graph.edges!.map((e, i) => {
      const s = e.sections![0]
      const points = [s.startPoint, ...(s.bendPoints ?? []), s.endPoint].map((p) => [round(p.x), round(p.y)] as Point)
      const label = e.labels?.[0]
      let labelAt: Point | undefined
      if (labels[i]) {
        // elkjs puts a label beside its edge; the label goes onto the segment of the edge across
        // the layers (horizontal to the right, vertical downwards) nearest to its centre, so that
        // it reads as the edge's own.
        const x = label!.x! + label!.width! / 2
        const y = label!.y! + label!.height! / 2
        // a is the axis along the layers, b the axis across them.
        const [a, b] = direction === 'RIGHT' ? [0, 1] : [1, 0]
        const centre = [x, y]
        const on = points.slice(1).map((q, k) => [points[k], q])
          .filter(([p, q]) => p[b] === q[b] && Math.min(p[a], q[a]) <= centre[a] && centre[a] <= Math.max(p[a], q[a]))
          .sort((s, t) => Math.abs(s[0][b] - centre[b]) - Math.abs(t[0][b] - centre[b]))[0]
        const at = [round(x), round(y)]
        if (on && direction === 'RIGHT') at[b] = on[0][b]
        labelAt = at as Point
      }
      return { from: edges[i].caller, to: edges[i].callee, ...(labelAt ? { label: labels[i], labelAt } : {}), points }
    })
  }
}

declare const data: Record<string, Graph>
export { data }

/** The graphs of every caller of calls.toml, by name, and of every edge, under the empty name. */
export default {
  watch: ['../../../figures/calls.toml', '../../../../agents/*.md', '../../../../skills/*/SKILL.md', '../../../../examples/models.toml'],
  async load(): Promise<Record<string, Graph>> {
    const calls: Call[] = parseToml(readFileSync(path.join(ROOT, 'docs', 'figures', 'calls.toml'), 'utf8')).call as Call[]
    const result: Record<string, Graph> = { '': await callGraph() }
    for (const caller of new Set(calls.map((c) => c.caller))) result[caller] = await callGraph(caller)
    return result
  }
}
