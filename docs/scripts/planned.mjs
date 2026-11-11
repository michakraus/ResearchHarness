// The check of the page Planned work, docs/src/planned.md, on the Markdown sources in docs/src/:
//
// - each link to planned.md#<id> names a row of planned.md: a `{#<id>}` in a line of one of its
//   tables;
// - each row of planned.md has a link from another page;
// - no page but planned.md holds a mark outside a link to planned.md. A mark is `(planned)`,
//   `(planned, …)`, `(work in progress)` or `(work in progress, …)`; a bold `**Planned:**` or
//   `**Work in progress:**`; or a table cell that starts or ends with the word `planned` or the
//   words `work in progress`, such as "macOS; on Linux planned". A mark whose word links another
//   target, such as planned.md with no row, is a mark too. Fenced blocks, code spans and HTML comments do not count, nor does the
//   plain word in a sentence, such as "a planned change" or "neither planned nor removed".
//
// Run it from docs/ with `node scripts/planned.mjs`. It prints one line for each problem and exits
// 1 when there is one.
import { readFileSync, readdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

/** The page of planned work, below docs/src/. */
export const PLANNED = 'planned.md'

const blank = (s) => s.replace(/[^\n]/g, ' ')
/** The line of the offset `i` in `text`, from 1. */
const lineAt = (text, i) => text.slice(0, i).split('\n').length
const isTableLine = (line) => /^\s*\|/.test(line)

/** The text of the Markdown `text` with its fenced blocks, code spans and HTML comments replaced
 * by spaces, so that the offsets and the line numbers stay. */
export function masked(text) {
  let fence = false
  const lines = text.split('\n').map((line) => {
    if (/^\s*(```|~~~)/.test(line)) {
      fence = !fence
      return blank(line)
    }
    return fence ? blank(line) : line
  })
  return lines.join('\n').replace(/<!--[\s\S]*?-->/g, blank).replace(/`[^`\n]*`/g, blank)
}

// A Markdown link: its text and its target.
const LINK = /\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^)\s]*)(?:\s+"[^"]*")?\)/g

/** The row that the link target `href` on the page `page` names, or null when the target is not
 * a fragment of planned.md. */
export function rowOf(page, href) {
  const hash = href.indexOf('#')
  if (hash < 0) return null
  const file = href.slice(0, hash)
  const target = file === '' ? page : path.posix.normalize(path.posix.join(path.posix.dirname(page), file))
  return target === PLANNED ? href.slice(hash + 1) : null
}

/** The rows of planned.md with the Markdown `text`: the `{#<id>}` of its table lines. */
export function rows(text) {
  const ids = []
  for (const line of masked(text).split('\n')) {
    if (isTableLine(line)) ids.push(...[...line.matchAll(/\{#([\w-]+)\}/g)].map((m) => m[1]))
  }
  return ids
}

/** The links to a row of planned.md on the page `page` with the Markdown `text`: each one's row
 * and line. */
export function links(page, text) {
  const body = masked(text)
  const found = []
  for (const m of body.matchAll(LINK)) {
    const row = rowOf(page, m[2])
    if (row !== null) found.push({ row, line: lineAt(body, m.index) })
  }
  return found
}

// The marks in a sentence: in parentheses, or bold at the start of a sentence. The word may be the
// text of a link that does not name a row of planned.md.
const WORD = '(?:planned|work in progress)'
const LINKED = `\\[?${WORD}(?:\\]\\([^)\\s]*\\))?`
const MARK = new RegExp(`\\(${LINKED}(?:,[^)]*)?\\)|\\*\\*${LINKED}:\\*\\*`, 'gi')
const CELL = new RegExp(`^${WORD}\\b|\\b${WORD}$`, 'i')

/** The problems of the marks on the page `page` with the Markdown `text`: a mark outside a link
 * to planned.md. */
export function markProblems(page, text) {
  if (page === PLANNED) return []
  // A link to a row of planned.md is the link of a mark: it does not count.
  const body = masked(text).replace(LINK, (link, _text, href) => (rowOf(page, href) === null ? link : blank(link)))
  const problems = []
  for (const m of body.matchAll(MARK)) {
    problems.push(`${page}:${lineAt(body, m.index)}: the mark "${m[0]}" has no link to ${PLANNED}`)
  }
  for (const [i, line] of body.split('\n').entries()) {
    if (!isTableLine(line)) continue
    for (const cell of line.trim().replace(/^\||\|$/g, '').split(/(?<!\\)\|/)) {
      const words = cell.replace(LINK, '$1').trim()
      if (CELL.test(words)) problems.push(`${page}:${i + 1}: the table cell "${words}" has no link to ${PLANNED}`)
    }
  }
  return problems
}

/** The problems of the pages `pages`, a map from a page below docs/src/ to its Markdown: a link
 * that names no row, a row with no link from another page, and a mark with no link. */
export function plannedProblems(pages) {
  const problems = []
  const known = new Set(rows(pages.get(PLANNED) ?? ''))
  if (!pages.has(PLANNED)) problems.push(`${PLANNED}: no such page`)
  const linked = new Set()
  for (const [page, text] of pages) {
    for (const { row, line } of links(page, text)) {
      if (!known.has(row)) problems.push(`${page}:${line}: the link to ${PLANNED}#${row} names no row`)
      if (page !== PLANNED) linked.add(row)
    }
    problems.push(...markProblems(page, text))
  }
  for (const row of known) {
    if (!linked.has(row)) problems.push(`${PLANNED}: the row #${row} has no link from another page`)
  }
  return problems
}

// The command: check the pages of docs/src/.
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const SRC = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src')
  const pages = new Map()
  for (const file of readdirSync(SRC, { recursive: true }).filter((f) => f.endsWith('.md')).sort()) {
    const page = file.split(path.sep).join('/')
    pages.set(page, readFileSync(path.join(SRC, file), 'utf8'))
  }
  const problems = plannedProblems(pages)
  for (const p of problems) console.log(p)
  console.log(`${pages.size} pages, ${rows(pages.get(PLANNED) ?? '').length} rows of planned work, ${problems.length} problems`)
  process.exit(problems.length === 0 ? 0 : 1)
}
