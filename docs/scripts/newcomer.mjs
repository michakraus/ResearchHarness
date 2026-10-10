// The check of the newcomer pages, on their Markdown sources in docs/src/:
//
// - the glossary of concepts.md has one entry, a `###` heading, for each term of TERMS;
// - on each newcomer page, the first use of each term links its glossary entry. A use is the
//   first match in prose: case-insensitive, a whole word, a plural -s counts, and the longest
//   term matches first, so that `sub-agent` and `coding agent` are not uses of `agent`. Fenced
//   blocks, code spans, headings, frontmatter, HTML lines such as a figure, and the text of a link
//   to another target do not count. On concepts.md, the glossary section does not count;
// - a newcomer page holds no file:line.
//
// Run it from docs/ with `node scripts/newcomer.mjs`. It prints one line for each problem and
// exits 1 when there is one.
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

/** The terms of the glossary. */
export const TERMS = [
  'coding agent', 'frontend', 'session', 'context', 'tool call', 'permission prompt', 'sandbox',
  'instruction file', 'rule', 'skill', 'agent', 'sub-agent', 'hook', 'tier', 'effort', 'profile',
  'tree instructions', 'install', 'drift'
]
/** The newcomer pages, below docs/src/. */
export const NEWCOMER = ['concepts.md', 'dependencies.md', 'setup-macos.md', 'tutorial.md', 'daily-use.md', 'profile.md']
/** The page of the glossary, and the anchor of a term's entry on it. */
export const GLOSSARY = 'concepts.md'
export const anchor = (term) => term.replaceAll(' ', '-')

const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
// The terms, longest first, with any white space between their words.
const ALTERNATIVES = [...TERMS].sort((a, b) => b.length - a.length).map((t) => escape(t).replaceAll(' ', '\\s+'))
const TERM = `(?<![\\w-])(${ALTERNATIVES.join('|')})s?(?![\\w-])`
const termOf = (text) => TERMS.find((t) => t === text.toLowerCase().replace(/\s+/g, ' '))

/** The text of the Markdown `text` with every part that is not prose replaced by spaces, so that
 * the offsets and the line numbers stay: frontmatter, fenced blocks, headings, HTML lines and
 * comments, container lines (`:::`), and, on the glossary page, the glossary section. */
export function prose(text, glossaryPage = false) {
  const blank = (s) => s.replace(/[^\n]/g, ' ')
  const lines = text.split('\n')
  let fence = false
  let front = lines[0] === '---'
  let glossary = false
  const out = lines.map((line, i) => {
    if (front) {
      if (i > 0 && line === '---') front = false
      return blank(line)
    }
    if (/^\s*(```|~~~)/.test(line)) {
      fence = !fence
      return blank(line)
    }
    if (fence) return blank(line)
    if (/^## /.test(line)) glossary = glossaryPage && /^## Glossary\s*$/.test(line)
    if (glossary || /^#{1,6} /.test(line) || /^\s*</.test(line) || /^\s*:::/.test(line)) return blank(line)
    return line
  })
  return out.join('\n').replace(/<!--[\s\S]*?-->/g, blank).replace(/<[^>\n]+>/g, blank)
}

/** The line of the offset `i` in `text`, from 1. */
const lineAt = (text, i) => text.slice(0, i).split('\n').length

/** Whether the link target `href` on `page` names the glossary entry of `term`. */
function linksEntry(page, href, term) {
  const target = page === GLOSSARY ? `#${anchor(term)}` : `${GLOSSARY}#${anchor(term)}`
  return href.replace(/^\.\//, '') === target
}

/** The problems of the first uses of the terms on the page `page` with the Markdown `text`. */
export function firstUseProblems(page, text, glossaryPage = page === GLOSSARY) {
  const body = prose(text, glossaryPage)
  // A code span, a link or an image, or a term.
  const scan = new RegExp(`(\`[^\`]*\`)|(!?\\[((?:[^\\[\\]]|\\[[^\\]]*\\])*)\\]\\(([^)\\s]*)(?:\\s+"[^"]*")?\\))|${TERM}`, 'gi')
  const seen = new Set()
  const problems = []
  for (const m of body.matchAll(scan)) {
    if (m[1] !== undefined) continue
    if (m[2] !== undefined) {
      // A link to a term's entry is a use of that term, if its text names the term.
      for (const t of m[3].matchAll(new RegExp(TERM, 'gi'))) {
        const term = termOf(t[1])
        if (!seen.has(term) && linksEntry(page, m[4], term)) seen.add(term)
      }
      continue
    }
    const term = termOf(m[5])
    if (seen.has(term)) continue
    seen.add(term)
    problems.push(`${page}:${lineAt(body, m.index)}: the first use of "${term}" has no link to its glossary entry`)
  }
  return problems
}

/** The problems of the glossary on the page text `text`: a term with no entry or with more than
 * one. */
export function entryProblems(text) {
  const section = /^## Glossary\s*$([\s\S]*?)(?=^## |(?![\s\S]))/m.exec(text)
  if (!section) return [`${GLOSSARY}: no section "## Glossary"`]
  const entries = [...section[1].matchAll(/^### (.+?)\s*$/gm)].map((m) => m[1].toLowerCase())
  const problems = []
  for (const term of TERMS) {
    const n = entries.filter((e) => e === term).length
    if (n === 0) problems.push(`${GLOSSARY}: the glossary has no entry "${term}"`)
    else if (n > 1) problems.push(`${GLOSSARY}: the glossary has ${n} entries "${term}"`)
  }
  return problems
}

/** The problems of the file:line references on the page `page` with the Markdown `text`. */
export function fileLineProblems(page, text) {
  const problems = []
  const ref = /(?<![\w/.~:-])((?:[\w.~-]+\/)*[\w.-]*[A-Za-z][\w.-]*:\d+(?:-\d+)?)(?![\w/])/g
  for (const m of text.matchAll(ref)) problems.push(`${page}:${lineAt(text, m.index)}: a file:line, ${m[1]}`)
  return problems
}

// The command: check the pages of docs/src/.
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const SRC = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src')
  const read = (page) => readFileSync(path.join(SRC, page), 'utf8')
  const problems = entryProblems(read(GLOSSARY))
  for (const page of NEWCOMER) {
    const text = read(page)
    problems.push(...firstUseProblems(page, text), ...fileLineProblems(page, text))
  }
  for (const p of problems) console.log(p)
  console.log(`${NEWCOMER.length} newcomer pages, ${TERMS.length} terms, ${problems.length} problems`)
  process.exit(problems.length === 0 ? 0 : 1)
}
