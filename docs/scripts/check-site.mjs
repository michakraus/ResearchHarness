// Checks of the built site in docs/build/, after `npm run docs:build`:
//
// - each page of the menu is a link of the sidebar on every page, and its HTML file exists;
// - the sidebar starts with Home, a top-level link, and then the group Getting started with the
//   introduction, the dependencies page, the two setup pages, the tutorial and the example tree,
//   in this order;
// - each link of a page's text to a heading of the site finds that heading, which VitePress's
//   check of dead links does not test;
// - the home page, whose home layout has no doc footer, has its own edit link;
// - each page has as many table rows as its Markdown source;
// - the home page has its two figures, the introduction its three and the page agents-at-work
//   its four call graphs, each found by its <title> and with a <desc>;
// - in every figure of the site, no edge crosses another edge or passes through a box that is
//   not its end (scripts/figures.mjs), and no figure loads a file from another host;
// - every colour of the style module of the figures has a value for the dark theme in the built
//   CSS, and no figure component or the generator names a colour itself.
//
// It prints one line for each problem and exits 1 when there is one.
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { figures as figuresOf, geometryProblems } from './figures.mjs'

const DOCS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const BUILD = path.join(DOCS, 'build')
const BASE = '/ResearchHarness/'

// The menu of the site: every page of docs/src/.
const MENU = [
  'index.md', 'concepts.md', 'dependencies.md', 'setup-macos.md', 'setup-linux.md', 'tutorial.md',
  'example-tree.md', 'daily-use.md', 'profile.md',
  'harness-command.md', 'agents-at-work.md', 'security.md', 'architecture.md',
  'components/agents.md', 'components/skills.md', 'components/commands.md',
  'components/rules.md', 'components/hooks.md', 'components/githooks.md',
  'components/scripts.md', 'components/adapters.md', 'components/harness.md',
  'components/other.md', 'development.md'
]

// The start of the sidebar: Home, then the group Getting started in this order.
const START = [
  'index.md', 'concepts.md', 'dependencies.md', 'setup-macos.md', 'setup-linux.md', 'tutorial.md',
  'example-tree.md'
]

const problems = []
const problem = (text) => problems.includes(text) || problems.push(text)

/** The URL path of a page, as the sidebar links it. */
const url = (page) => BASE + page.replace(/(^|\/)index\.md$/, '$1').replace(/\.md$/, '')
/** The built HTML file of a page. */
const html = (page) => path.join(BUILD, page.replace(/\.md$/, '.html'))
/** The Markdown source of a page. */
const source = (page) => path.join(DOCS, 'src', page)

const between = (text, start, end) => {
  const i = text.indexOf(start)
  const j = i < 0 ? -1 : text.indexOf(end, i)
  return j < 0 ? '' : text.slice(i, j)
}
const hrefs = (text) => [...text.matchAll(/<a [^>]*?href="([^"]*)"/g)].map((m) => m[1])
/** The content of a built page: its <main> element, or on the home page, whose home layout has no
 * <main>, the home layout's container up to the page's scripts. An empty content is a problem. */
const content = (page, text) => {
  const region = page === 'index.md' ? between(text, 'class="VPHome"', '<script') : between(text, '<main', '</main>')
  if (region === '') problem(`${page}: no content region in the built page`)
  return region
}

const built = new Map()
for (const page of MENU) {
  if (!existsSync(html(page))) {
    problem(`${page}: no ${path.relative(DOCS, html(page))}`)
    continue
  }
  built.set(page, readFileSync(html(page), 'utf8'))
}

// The sidebar of every page links every page of the menu. The home page is a landing page with
// VitePress's home layout, which has no sidebar.
for (const [page, text] of built) {
  if (page === 'index.md') continue
  const sidebar = hrefs(between(text, 'id="VPSidebarNav"', '</nav>'))
  if (sidebar.length === 0) problem(`${page}: no sidebar`)
  for (const target of MENU) {
    if (!sidebar.includes(url(target))) problem(`${page}: the sidebar has no link to ${target}`)
  }
  const first = sidebar.slice(0, START.length).join(' ')
  if (first !== START.map(url).join(' ')) problem(`${page}: the sidebar starts with ${first}, not ${START.join(', ')}`)
  // Home is a headline of its own, a link at the top level, above the group Getting started.
  const nav = between(text, 'id="VPSidebarNav"', '</nav>')
  const home = /<div class="VPSidebarItem level-0 is-link"[^>]*>(?:(?!<\/a>)[\s\S])*?href="([^"]*)"/.exec(nav)
  if (!home || home[1] !== url('index.md') || home.index > nav.indexOf('>Getting started</h2>')) problem(`${page}: Home is not a top-level link above the group Getting started`)
}

// A link with a fragment finds a heading of its page.
const ids = (text) => new Set([...text.matchAll(/ id="([^"]*)"/g)].map((m) => m[1]))
const byUrl = new Map([...built].map(([page, text]) => [url(page), ids(text)]))
let fragments = 0
for (const [page, text] of built) {
  for (const href of hrefs(content(page, text))) {
    const link = new URL(href, `https://site${url(page)}`)
    if (link.host !== 'site' || link.hash === '') continue
    fragments++
    const known = byUrl.get(link.pathname)
    if (!known) problem(`${page}: the link ${href} names no page of the menu`)
    else if (!known.has(decodeURIComponent(link.hash.slice(1)))) problem(`${page}: the link ${href} names no heading`)
  }
}

// The home page has an edit link to its source. Its home layout shows no doc footer, so the page
// draws the link itself.
const EDIT = 'https://github.com/michakraus/ResearchHarness/edit/main/docs/src/index.md'
if (built.has('index.md') && !hrefs(content('index.md', built.get('index.md'))).includes(EDIT)) {
  problem(`index.md: no edit link to ${EDIT}`)
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
  const trs = (content(page, text).match(/<tr>/g) ?? []).length
  if (trs !== rows) problem(`${page}: ${rows} table rows in the source, ${trs} in the site`)
}

// The figures of the site, in the HTML of each page: the SVG that the build renders. The pages
// below have these figures, by their <title>, and no other page has one.
const FIGURES = {
  'index.md': ['The harness and its three layers', 'From the sources to the frontends'],
  'concepts.md': ['The harness and its three layers', 'The harness, the profile and the tree instructions', 'The layers of control around one tool call'],
  'agents-at-work.md': ['The calls of build-part', 'The calls of build-reviewed', 'The calls of julia-pr-shepherd', 'Every spawn']
}
let figures = 0
for (const [page, text] of built) {
  const found = figuresOf(text)
  figures += found.length
  const titles = found.map((f) => f.title)
  const expected = FIGURES[page] ?? []
  for (const title of expected) {
    if (!titles.includes(title)) problem(`${page}: no figure with the title "${title}"`)
  }
  for (const title of titles) {
    if (!expected.includes(title)) problem(`${page}: a figure that the check does not know: "${title}"`)
  }
  for (const f of found) {
    const name = `${page}: the figure "${f.title || '(no title)'}"`
    if (f.title === '') problem(`${name} has no <title>`)
    if (f.desc === '') problem(`${name} has no <desc>`)
    if (f.boxes.length === 0) problem(`${name} has no box`)
    for (const url of f.external) problem(`${name} loads ${url} from another host`)
    if (f.images > 0) problem(`${name} holds an image or a foreign object, not SVG shapes`)
    for (const p of geometryProblems(f)) problem(`${name}: ${p}`)
  }
}

// Each colour of the style module of the figures, a custom property `--fig-…` whose value under
// :root is a colour, has a value under .dark too, in the built CSS.
const COLOUR = /^(?:#[0-9a-fA-F]{3,8}|rgba?\(.*\)|hsla?\(.*\))$/
const light = new Map()
const dark = new Map()
for (const file of readdirSync(path.join(BUILD, 'assets')).filter((f) => f.endsWith('.css'))) {
  const css = readFileSync(path.join(BUILD, 'assets', file), 'utf8')
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selectors = m[1].split(',').map((s) => s.trim())
    for (const d of m[2].matchAll(/(--fig-[\w-]+)\s*:\s*([^;]+)/g)) {
      if (selectors.includes(':root')) light.set(d[1], d[2].trim())
      if (selectors.includes('.dark')) dark.set(d[1], d[2].trim())
    }
  }
}
const colours = [...light].filter(([, value]) => COLOUR.test(value)).map(([name]) => name)
if (colours.length === 0) problem('the built CSS has no colour of the style module of the figures under :root')
for (const name of colours) {
  if (!dark.has(name)) problem(`the colour ${name} of the figures has no value under .dark`)
}

// The figure components and their generator name no colour: every colour is in the style module.
const FIGURE_SOURCES = path.join(DOCS, '.vitepress', 'theme', 'figures')
for (const file of readdirSync(FIGURE_SOURCES)) {
  const lines = readFileSync(path.join(FIGURE_SOURCES, file), 'utf8').split('\n')
  for (const [i, line] of lines.entries()) {
    if (/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/.test(line)) problem(`docs/.vitepress/theme/figures/${file}:${i + 1} names a colour; use a property of figures.css`)
  }
}

for (const p of problems) console.log(p)
console.log(`${built.size} pages, ${fragments} links to a heading, ${figures} figures, ${colours.length} figure colours, ${problems.length} problems`)
process.exit(problems.length === 0 ? 0 : 1)
