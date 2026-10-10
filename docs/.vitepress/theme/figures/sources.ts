// The facts of the agents and skills that the figures show, read from their sources at build time:
// the kind of each, its tier, and the two grey lines of its card, its model and its effort. The
// call graphs (calls.data.ts) and the walk-throughs (walkthroughs.data.ts) read them here.
import { readFileSync, existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse as parseToml } from 'smol-toml'
import { parse as parseYaml } from 'yaml'

/** The root of the repository. */
export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..')

/** The frontmatter of the Markdown file `file`, read as YAML. */
function frontmatter(file: string) {
  const m = /^---\n([\s\S]*?)\n---\n/.exec(readFileSync(file, 'utf8'))
  if (!m) throw new Error(`${file} has no frontmatter`)
  return parseYaml(m[1])
}

/** The Claude Code model of each tier: the [claude] table of examples/models.toml. */
export function claudeModels(): Record<string, string> {
  return parseToml(readFileSync(path.join(ROOT, 'examples', 'models.toml'), 'utf8')).claude as Record<string, string>
}

/** The name, kind, tier and the two grey lines (model, effort) of the agent or skill `name`. The
 * tier is the source's `model:`, or undefined where it has none. */
export function node(name: string, models: Record<string, string>) {
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
  return { name, kind, tier: meta.model as string | undefined, lines: [`${kind} on ${model}`, `effort: ${effort}`] } as const
}
