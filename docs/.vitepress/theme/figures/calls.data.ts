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
  const graph = await elk.layout({
    id: 'root',
    layoutOptions: { ...LAYOUT, 'elk.direction': 'RIGHT' },
    children: nodes.map((n) => ({ id: n.name, width: cardWidth(n.name, [...n.lines]), height: cardHeight(2) })),
    edges: edges.map((c, i) => ({
      id: `e${i}`,
      sources: [c.caller],
      targets: [c.callee],
      labels: labels[i] ? [{ text: labels[i], width: textWidth(labels[i], LABEL_SIZE) + 10, height: 18 }] : []
    }))
  })
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
      return {
        from: edges[i].caller,
        to: edges[i].callee,
        ...(labels[i] ? { label: labels[i], labelAt: [round(label!.x! + label!.width! / 2), round(label!.y! + label!.height! / 2)] as Point } : {}),
        points
      }
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
