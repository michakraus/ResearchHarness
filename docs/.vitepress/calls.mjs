// The call graphs of docs/src/agents-at-work.md, as Mermaid text.
//
// The edges come from docs/figures/calls.toml: one entry for each spawn. The kind of each node
// comes from where its source is, its effort from the source's frontmatter, and an agent's model
// from its tier and the [claude] table of examples/models.toml. Every build reads these files
// again, so a figure changes when a source changes. `harness test` checks calls.toml.
//
// A page asks for a graph with a fenced block whose info string is `calls <root>`, or `calls` for
// every edge. The block holds the graph's `accTitle:` and `accDescr:` lines. `callsMarkdown`
// turns the block into a `mermaid` block, which vitepress-plugin-mermaid draws.

import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { parse as parseToml } from 'smol-toml'
import { parse as parseYaml } from 'yaml'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')

/** The frontmatter of the Markdown file `file`, read as YAML. */
function frontmatter(file) {
  const m = /^---\n([\s\S]*?)\n---\n/.exec(readFileSync(file, 'utf8'))
  if (!m) throw new Error(`${file} has no frontmatter`)
  return parseYaml(m[1])
}

/** The name, kind, model and effort of the agent or skill `name`. */
function node(name, models) {
  const agent = path.join(ROOT, 'agents', `${name}.md`)
  const kind = existsSync(agent) ? 'agent' : 'skill'
  const meta = frontmatter(kind === 'agent' ? agent : path.join(ROOT, 'skills', name, 'SKILL.md'))
  let model
  // A skill runs in the session that loads it, on the session's model, whatever its `model:`.
  if (kind === 'skill') model = "the session's model"
  else if (meta.model === undefined) model = "the caller's model"
  else if (models[meta.model] === undefined) throw new Error(`${name}: no model for the tier ${meta.model}`)
  else model = models[meta.model]
  const effort = meta.effort ?? "the session's effort"
  return { name, kind, model, effort }
}

/** The entries of `calls` that `root` reaches: its own spawns, then their callees' spawns. */
function reached(calls, root) {
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

/** Text for a Mermaid label in double quotes. */
const text = (s) => s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;')

const id = (name) => name.replaceAll('-', '_')

/** The Mermaid text of the call graph of `root`, or of every edge when `root` is undefined. The
 * lines of `head` (the `accTitle:` and `accDescr:` lines) come first. */
export function callGraph(root, head = '') {
  const calls = parseToml(readFileSync(path.join(ROOT, 'docs', 'figures', 'calls.toml'), 'utf8')).call
  const models = parseToml(readFileSync(path.join(ROOT, 'examples', 'models.toml'), 'utf8')).claude
  if (root !== undefined && !calls.some((c) => c.caller === root)) {
    throw new Error(`calls.toml has no edge from ${root}`)
  }
  const edges = reached(calls, root)
  const names = [...new Set(edges.flatMap((c) => [c.caller, c.callee]))]
  const lines = [root === undefined ? 'flowchart LR' : 'flowchart TB']
  for (const line of head.split('\n')) if (line.trim()) lines.push(`  ${line.trim()}`)
  for (const n of names.map((name) => node(name, models))) {
    lines.push(`  ${id(n.name)}("<b>${text(n.name)}</b><br/>${text(`${n.kind} on ${n.model}`)}<br/>${text(`effort: ${n.effort}`)}")`)
    lines.push(`  class ${id(n.name)} ${n.kind}`)
  }
  for (const c of edges) {
    const label = [c.label, c.effort && `at ${c.effort} effort`].filter(Boolean).join(', ')
    lines.push(`  ${id(c.caller)} -->${label ? `|"${text(label)}"|` : ''} ${id(c.callee)}`)
  }
  return lines.join('\n') + '\n'
}

/** A markdown-it plugin that turns each `calls` block into a `mermaid` block. */
export function callsMarkdown(md) {
  md.core.ruler.push('calls', (state) => {
    for (const token of state.tokens) {
      const m = token.type === 'fence' && /^calls(?:\s+(\S+))?\s*$/.exec(token.info)
      if (!m) continue
      token.content = callGraph(m[1], token.content)
      token.info = 'mermaid'
    }
  })
}
