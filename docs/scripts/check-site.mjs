// Checks of the built site in docs/build/, after `npm run docs:build`:
//
// - each page of the menu is a link of the sidebar on every page, and its HTML file exists;
// - each link of a page's text to a heading of the site finds that heading, which VitePress's
//   check of dead links does not test;
// - each page has as many table rows as its Markdown source;
// - the page agents-at-work has its four call graphs, each with `accTitle` and `accDescr`.
//
// It prints one line for each problem and exits 1 when there is one.
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const DOCS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const BUILD = path.join(DOCS, 'build')
const BASE = '/ResearchHarness/'

// The menu of the site: every page of docs/src/, which the Documenter site had in its menu too.
const MENU = [
  'index.md', 'tutorial.md', 'setup-macos.md', 'setup-linux.md', 'daily-use.md', 'profile.md',
  'harness-command.md', 'agents-at-work.md', 'security.md', 'architecture.md', 'tools.md',
  'components/agents.md', 'components/skills.md', 'components/commands.md',
  'components/rules.md', 'components/hooks.md', 'components/githooks.md',
  'components/scripts.md', 'components/adapters.md', 'components/harness.md',
  'components/other.md', 'development.md'
]

const problems = []
const problem = (text) => problems.push(text)

/** The URL path of a page, as the sidebar links it. */
const url = (page) => BASE + page.replace(/(^|\/)index\.md$/, '$1').replace(/\.md$/, '')
/** The built HTML file of a page. */
const html = (page) => path.join(BUILD, page.replace(/\.md$/, '.html'))
/** The Markdown source of a page; the home page includes the README. */
const source = (page) => path.join(DOCS, '..', page === 'index.md' ? 'README.md' : path.join('docs', 'src', page))

const between = (text, start, end) => {
  const i = text.indexOf(start)
  const j = i < 0 ? -1 : text.indexOf(end, i)
  return j < 0 ? '' : text.slice(i, j)
}
const hrefs = (text) => [...text.matchAll(/<a [^>]*?href="([^"]*)"/g)].map((m) => m[1])

const built = new Map()
for (const page of MENU) {
  if (!existsSync(html(page))) {
    problem(`${page}: no ${path.relative(DOCS, html(page))}`)
    continue
  }
  built.set(page, readFileSync(html(page), 'utf8'))
}

// The sidebar of every page links every page of the menu.
for (const [page, text] of built) {
  const sidebar = hrefs(between(text, 'id="VPSidebarNav"', '</nav>'))
  if (sidebar.length === 0) problem(`${page}: no sidebar`)
  for (const target of MENU) {
    if (!sidebar.includes(url(target))) problem(`${page}: the sidebar has no link to ${target}`)
  }
}

// A link with a fragment finds a heading of its page.
const ids = (text) => new Set([...text.matchAll(/ id="([^"]*)"/g)].map((m) => m[1]))
const byUrl = new Map([...built].map(([page, text]) => [url(page), ids(text)]))
let fragments = 0
for (const [page, text] of built) {
  for (const href of hrefs(between(text, '<main', '</main>'))) {
    const link = new URL(href, `https://site${url(page)}`)
    if (link.host !== 'site' || link.hash === '') continue
    fragments++
    const known = byUrl.get(link.pathname)
    if (!known) problem(`${page}: the link ${href} names no page of the menu`)
    else if (!known.has(decodeURIComponent(link.hash.slice(1)))) problem(`${page}: the link ${href} names no heading`)
  }
}

// Each page keeps the rows of its tables: the header and body rows of the Markdown tables, outside
// code blocks, against the <tr> of the built page.
for (const [page, text] of built) {
  let fence = false
  let rows = 0
  for (const line of readFileSync(source(page), 'utf8').split('\n')) {
    if (/^\s*(```|~~~)/.test(line)) fence = !fence
    else if (!fence && /^\s*\|/.test(line) && !/^\s*\|[\s:|-]+\|\s*$/.test(line)) rows++
  }
  const trs = (between(text, '<main', '</main>').match(/<tr>/g) ?? []).length
  if (trs !== rows) problem(`${page}: ${rows} table rows in the source, ${trs} in the site`)
}

// The four call graphs of agents-at-work, in the page's script.
const chunk = readdirSync(path.join(BUILD, 'assets')).find((f) => /^agents-at-work\.md\.[^.]+\.js$/.test(f))
const graphs = chunk === undefined ? [] :
  [...readFileSync(path.join(BUILD, 'assets', chunk), 'utf8').matchAll(/graph:"([^"]*)"/g)].map((m) => decodeURIComponent(m[1]))
if (graphs.length !== 4) problem(`agents-at-work.md: ${graphs.length} call graphs, not 4`)
for (const [i, graph] of graphs.entries()) {
  if (!/^\s*accTitle: \S/m.test(graph) || !/^\s*accDescr: \S/m.test(graph)) {
    problem(`agents-at-work.md: call graph ${i + 1} has no accTitle or no accDescr`)
  }
}

for (const p of problems) console.log(p)
console.log(`${built.size} pages, ${fragments} links to a heading, ${graphs.length} call graphs, ${problems.length} problems`)
process.exit(problems.length === 0 ? 0 : 1)
