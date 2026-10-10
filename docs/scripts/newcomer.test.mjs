// Cases of scripts/newcomer.mjs, the check of the newcomer pages. Run with
// `node --test scripts/newcomer.test.mjs`, which `npm run docs:check` does first.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { TERMS, entryProblems, fileLineProblems, firstUseProblems } from './newcomer.mjs'

const G = 'concepts.md'
const uses = (page, text) => firstUseProblems(page, text, page === G)

test('the set of terms is the nineteen terms of clause 2', () => {
  assert.equal(TERMS.length, 19)
  assert.equal(new Set(TERMS).size, 19)
})

test('an unlinked first use names the page, the line and the term', () => {
  const text = 'Line one.\nThe sandbox stops it.\nThe [sandbox](concepts.md#sandbox) again.\n'
  assert.deepEqual(uses('daily-use.md', text), ['daily-use.md:2: the first use of "sandbox" has no link to its glossary entry'])
})

test('a linked first use passes, and a later use needs no link', () => {
  assert.deepEqual(uses('daily-use.md', 'The [sandbox](concepts.md#sandbox) stops it. The sandbox again.\n'), [])
})

test('the longest term matches first: sub-agent and coding agent are not uses of agent', () => {
  const text = 'A [sub-agent](concepts.md#sub-agent) and a [coding agent](concepts.md#coding-agent).\nAn agent.\n'
  assert.deepEqual(uses('tutorial.md', text), ['tutorial.md:2: the first use of "agent" has no link to its glossary entry'])
})

test('a plural -s counts, the case does not, and a term may wrap to the next line', () => {
  assert.deepEqual(uses('tutorial.md', 'Two Sessions.\n'), ['tutorial.md:1: the first use of "session" has no link to its glossary entry'])
  assert.deepEqual(uses('tutorial.md', 'Each tool\ncall shows.\n'), ['tutorial.md:1: the first use of "tool call" has no link to its glossary entry'])
  assert.deepEqual(uses('tutorial.md', 'The [tool\ncalls](concepts.md#tool-call) show.\n'), [])
})

test('a whole word only: a hyphen or a letter next to the term makes another word', () => {
  assert.deepEqual(uses('tutorial.md', 'It is sandboxed. Run skill-triggers. A reinstall.\n'), [])
})

test('code spans, fenced blocks, headings, frontmatter, figures and other links do not count', () => {
  const text = [
    '---', 'title: the session', '---', '# The session', '', '```bash', 'harness install', '```',
    'Run `harness install` now.', '<OverviewFigure />', 'See [the session page](daily-use.md).',
    '<!-- a hook -->', '::: tip Without a profile', ':::', ''
  ].join('\n')
  assert.deepEqual(uses('tutorial.md', text), [])
})

test('a link to the entry of another term is the text of another link', () => {
  const text = 'A [hook refuses](concepts.md#sandbox) it.\nA hook.\n'
  assert.deepEqual(uses('tutorial.md', text), ['tutorial.md:2: the first use of "hook" has no link to its glossary entry'])
})

test('on the glossary page, an anchor of the page links the entry, and the glossary section does not count', () => {
  const text = 'The [sandbox](#sandbox) limits it.\n\n## Glossary\n\n### Hook\n\nA hook is a program.\n\n## After\n\nA hook.\n'
  assert.deepEqual(uses(G, text), [`${G}:11: the first use of "hook" has no link to its glossary entry`])
})

test('a page other than the glossary page links the entry through concepts.md, with or without ./', () => {
  assert.deepEqual(uses('tutorial.md', 'The [sandbox](./concepts.md#sandbox) limits it.\n'), [])
  // `#sandbox` on another page is a link to another target: its text does not count.
  assert.deepEqual(uses('tutorial.md', 'The [sandbox](#sandbox) limits it.\nThe sandbox.\n'), ['tutorial.md:2: the first use of "sandbox" has no link to its glossary entry'])
})

test('each term has one entry: a missing entry and a second entry are named', () => {
  const entries = TERMS.map((t) => `### ${t[0].toUpperCase()}${t.slice(1)}\n\nText.\n`)
  const page = (list) => `# Concepts\n\n## Glossary\n\n${list.join('\n')}\n## Next\n\n### Tier\n`
  assert.deepEqual(entryProblems(page(entries)), [])
  assert.deepEqual(entryProblems(page(entries.filter((e) => !e.startsWith('### Tier')))), [`${G}: the glossary has no entry "tier"`])
  assert.deepEqual(entryProblems(page([...entries, '### Tier\n'])), [`${G}: the glossary has 2 entries "tier"`])
  assert.deepEqual(entryProblems('# Concepts\n'), [`${G}: no section "## Glossary"`])
})

test('a file:line is named, a URL with a port and a time are not', () => {
  const text = 'Call sites: `.githooks/pre-push:56`, bin/harness:1 and `hooks/cc-status:11-12`.\n' +
    'A server at http://127.0.0.1:8080 at 10:30, step 2: done.\n'
  assert.deepEqual(fileLineProblems('dependencies.md', text), [
    'dependencies.md:1: a file:line, .githooks/pre-push:56',
    'dependencies.md:1: a file:line, bin/harness:1',
    'dependencies.md:1: a file:line, hooks/cc-status:11-12'
  ])
})
