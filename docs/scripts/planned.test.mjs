// Cases of scripts/planned.mjs, the check of the page Planned work. Run with
// `node --test scripts/planned.test.mjs`, which `npm run docs:check` does first.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { PLANNED, links, markProblems, plannedProblems, rowOf, rows } from './planned.mjs'

const PAGE = [
  '# Planned work', '', '| feature | state | described in |', '|:--|:--|:--|',
  '| **Masked keys**{#masked-keys} | planned | [Sandboxes](safeguards/sandbox.md#planned) |',
  '| **A credential proxy**{#credential-proxy} | planned; after [masked keys](#masked-keys) | [Sandboxes](safeguards/sandbox.md#planned) |', ''
].join('\n')
const SANDBOX = 'The keys ([planned](../planned.md#masked-keys)) and a proxy ([planned](../planned.md#credential-proxy), last).\n'
const check = (extra) => plannedProblems(new Map([[PLANNED, PAGE], ['safeguards/sandbox.md', SANDBOX], ...extra]))
const marks = (text) => markProblems('safeguards/sandbox.md', text)

test('the rows are the {#id} of the table lines of planned.md, not of a heading or a code block', () => {
  assert.deepEqual(rows(PAGE), ['masked-keys', 'credential-proxy'])
  assert.deepEqual(rows('## Masked keys {#masked-keys}\n\n```\n| x{#code} |\n```\n'), [])
})

test('a link names a row of planned.md by its path from the linking page', () => {
  assert.equal(rowOf('safeguards/sandbox.md', '../planned.md#masked-keys'), 'masked-keys')
  assert.equal(rowOf('development.md', './planned.md#masked-keys'), 'masked-keys')
  assert.equal(rowOf(PLANNED, '#masked-keys'), 'masked-keys')
  assert.equal(rowOf('safeguards/sandbox.md', 'planned.md#masked-keys'), null)
  assert.equal(rowOf('safeguards/sandbox.md', '../planned.md'), null)
  assert.equal(rowOf('safeguards/sandbox.md', '#planned'), null)
  assert.deepEqual(links('agentic/edges.md', 'One.\n**[Planned](../planned.md#edge-removal):** an entry goes.\n'), [{ row: 'edge-removal', line: 2 }])
})

test('(a) a link to a row that planned.md does not hold fails, a link to a row it holds passes', () => {
  assert.deepEqual(check([]), [])
  assert.deepEqual(check([['agentic/edges.md', 'A ([planned](../planned.md#gone)) entry.\n']]), [
    'agentic/edges.md:1: the link to planned.md#gone names no row'
  ])
  assert.deepEqual(check([['agentic/edges.md', 'A ([planned](../planned.md#masked-keys)) entry.\n']]), [])
})

test('(b) a row with no link from another page fails, also when planned.md links it itself', () => {
  assert.deepEqual(plannedProblems(new Map([[PLANNED, PAGE], ['safeguards/sandbox.md', 'The keys ([planned](../planned.md#masked-keys)).\n']])), [
    'planned.md: the row #credential-proxy has no link from another page'
  ])
  const unlinked = new Map([[PLANNED, PAGE], ['safeguards/sandbox.md', 'A proxy ([planned](../planned.md#credential-proxy)).\n']])
  assert.deepEqual(plannedProblems(unlinked), ['planned.md: the row #masked-keys has no link from another page'])
})

test('(c) each mark form without a link to a row fails, with the page and the line', () => {
  assert.deepEqual(marks('One.\n- **Masked keys** (planned): the keys.\n'), [
    'safeguards/sandbox.md:2: the mark "(planned)" has no link to planned.md'
  ])
  assert.deepEqual(marks('- **A token** (planned, waits for your tokens): one.\n'), [
    'safeguards/sandbox.md:1: the mark "(planned, waits for your tokens)" has no link to planned.md'
  ])
  assert.deepEqual(marks('- **The profiles** (work in progress): bwrap.\n'), [
    'safeguards/sandbox.md:1: the mark "(work in progress)" has no link to planned.md'
  ])
  assert.deepEqual(marks('They run unwrapped. **Work in progress:** a wrapper.\n'), [
    'safeguards/sandbox.md:1: the mark "**Work in progress:**" has no link to planned.md'
  ])
  assert.deepEqual(marks('No rule removes an entry. **Planned:** an entry goes.\n'), [
    'safeguards/sandbox.md:1: the mark "**Planned:**" has no link to planned.md'
  ])
  assert.deepEqual(marks('| sandbox | on |\n|:--|:--|\n| agentbox | macOS; on Linux planned |\n| daemons | macOS; on Linux work in progress |\n'), [
    'safeguards/sandbox.md:3: the table cell "macOS; on Linux planned" has no link to planned.md',
    'safeguards/sandbox.md:4: the table cell "macOS; on Linux work in progress" has no link to planned.md'
  ])
  assert.deepEqual(marks('| check | blocks |\n|:--|:--|\n| ast-grep rules | planned for every commit |\n'), [
    'safeguards/sandbox.md:3: the table cell "planned for every commit" has no link to planned.md'
  ])
})

test('(c) a mark whose word links planned.md with no row, or another page, fails', () => {
  assert.deepEqual(marks('- **Masked keys** ([planned](../planned.md)): the keys.\n'), [
    'safeguards/sandbox.md:1: the mark "([planned](../planned.md))" has no link to planned.md'
  ])
  assert.deepEqual(marks('They run. **[Planned](#planned):** a wrapper.\n'), [
    'safeguards/sandbox.md:1: the mark "**[Planned](#planned):**" has no link to planned.md'
  ])
  assert.deepEqual(marks('| agentbox | macOS; on Linux [planned](#planned) |\n'), [
    'safeguards/sandbox.md:1: the table cell "macOS; on Linux planned" has no link to planned.md'
  ])
})

test('(c) each mark form with a link to its row passes', () => {
  const text = [
    '- **Masked keys** ([planned](../planned.md#masked-keys)): the keys.',
    '- **A token** ([planned](../planned.md#token-per-owner), waits for your tokens): one.',
    '- **The profiles** ([work in progress](../planned.md#daemon-profiles-linux)): bwrap.',
    'They run unwrapped. **[Work in progress](../planned.md#daemon-profiles-linux):** a wrapper.',
    '**[Planned](../planned.md#edge-removal):** an entry goes.',
    '| agentbox | macOS; on Linux [planned](../planned.md#linux-launcher) |', ''
  ].join('\n')
  assert.deepEqual(marks(text), [])
})

test('the plain word in a sentence, in a code span, in a heading or in a table cell passes', () => {
  const text = [
    '## Planned', '', '## Planned safeguards', '',
    'a long or a wide job. For a planned change, one agent builds and another agent judges.',
    'order of `frontends.py` (`frontends.planned`); without `[setup]`, every frontend is chosen.',
    'frontend that `[setup]` does not choose is neither planned nor removed. The installed',
    'It loads when the user wants a task planned or split into pull requests, asks what can run in',
    'This page lists the static checks, where each one runs, and the checks that are planned.',
    'The [planned safeguards](security-model.md#planned-safeguards) close some of them.',
    '| `Packages` | the packages | the agents and skills of a planned change and of a pull request |',
    '| `x` | `(planned)` |', '', '```', '- **A guard** (planned): a hook.', '```',
    '<!-- **Planned:** a note -->', ''
  ].join('\n')
  assert.deepEqual(marks(text), [])
})

test('planned.md itself holds no mark: its state cells say planned', () => {
  assert.deepEqual(markProblems(PLANNED, PAGE), [])
})
