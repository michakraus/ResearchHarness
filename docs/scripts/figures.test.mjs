// Cases of scripts/figures.mjs, the reader of a built figure and its geometry checks. Run with
// `node --test scripts/`, which `npm run docs:check` does first.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { figures, geometryProblems, meet, points } from './figures.mjs'

const box = (name, x, y, w, h) => `<rect data-box="${name}" x="${x}" y="${y}" width="${w}" height="${h}"/>`
const edge = (from, to, d) => `<path data-edge="${from} → ${to}" data-from="${from}" data-to="${to}" d="${d}"/>`
const svg = (body, title = 'T', desc = 'D') =>
  `<p>text</p><svg class="icon"><path d="M0 0"/></svg><svg role="img" viewBox="0 0 400 400"><title>${title}</title><desc>${desc}</desc>` +
  `<svg viewBox="0 0 24 24"><path d="M1 1L2 2"/></svg>${body}</svg><svg class="icon"></svg>`
const one = (body) => {
  const found = figures(svg(body))
  assert.equal(found.length, 1)
  return found[0]
}

test('points takes the end point of each command', () => {
  assert.deepEqual(points('M0 0L10 0Q20 0 20 10V30H5'), [[0, 0], [10, 0], [20, 10], [20, 30], [5, 30]])
})

test('a figure ends at the </svg> of its own start tag, past the nested icons and an icon before it', () => {
  const f = one(box('a', 0, 0, 10, 10))
  assert.equal(f.title, 'T')
  assert.equal(f.desc, 'D')
  assert.equal(f.boxes.length, 1)
  assert.deepEqual(figures('<svg viewBox="0 0 1 1"></svg>'), [])
})

test('two segments that cross meet in one point; parallel ones do not meet', () => {
  assert.deepEqual(meet([[0, 5], [10, 5]], [[5, 0], [5, 10]]), [[5, 5]])
  assert.deepEqual(meet([[0, 0], [10, 0]], [[0, 1], [10, 1]]), [])
  assert.equal(meet([[0, 0], [10, 0]], [[5, 0], [20, 0]]).length, 2)
})

test('two edges that cross are named', () => {
  const f = one(box('a', 0, 0, 20, 20) + box('b', 100, 100, 20, 20) + box('c', 0, 100, 20, 20) + box('d', 100, 0, 20, 20) +
    edge('a', 'b', 'M20 10L60 10L60 110L100 110') + edge('c', 'd', 'M20 110L40 110L40 50L80 50L80 10L100 10'))
  assert.deepEqual(geometryProblems(f), ['the edges a → b and c → d cross at (60, 50)'])
})

test('two edges that leave one box on a shared trunk, or meet only in that box, pass', () => {
  const f = one(box('a', 0, 0, 20, 40) + box('b', 100, 0, 20, 20) + box('c', 100, 100, 20, 20) +
    edge('a', 'b', 'M20 10L100 10') + edge('a', 'c', 'M20 10L60 10L60 110L100 110'))
  assert.deepEqual(geometryProblems(f), [])
  const g = one(box('a', 0, 0, 20, 40) + box('b', 100, 0, 20, 20) + box('c', 100, 100, 20, 20) +
    edge('a', 'b', 'M20 10L100 10') + edge('a', 'c', 'M10 40L10 110L100 110'))
  assert.deepEqual(geometryProblems(g), [])
  const h = one(box('a', 0, 0, 20, 40) + box('b', 100, 100, 20, 20) + box('c', 100, 0, 20, 40) +
    edge('a', 'b', 'M20 30L40 30L40 110L100 110') + edge('a', 'c', 'M20 10L40 10L40 30L100 30'))
  assert.equal(geometryProblems(h).length, 1, 'two edges of one box that meet after different paths cross')
})

test('two edges of one box that part and then cross are named', () => {
  const f = one(box('a', 0, 0, 20, 40) + box('b', 100, 100, 20, 20) + box('c', 100, 20, 20, 20) +
    edge('a', 'b', 'M20 10L60 10L60 110L100 110') + edge('a', 'c', 'M20 30L100 30'))
  assert.deepEqual(geometryProblems(f), ['the edges a → b and a → c cross at (60, 30)'])
})

test('an edge that runs along another edge outside their common box is a crossing', () => {
  const f = one(box('a', 0, 0, 20, 20) + box('b', 200, 0, 20, 20) + box('c', 0, 100, 20, 20) + box('d', 200, 100, 20, 20) +
    edge('a', 'b', 'M20 10L200 10') + edge('c', 'd', 'M20 110L80 110L80 10L120 10L120 110L200 110'))
  assert.equal(geometryProblems(f).length, 1)
})

test('an edge through a box that is not its end is named; a panel around an end is not', () => {
  const f = one(box('panel', 0, 0, 60, 60) + box('a', 10, 10, 20, 20) + box('x', 100, 0, 20, 40) + box('b', 200, 10, 20, 20) +
    edge('a', 'b', 'M30 20L200 20'))
  assert.deepEqual(geometryProblems(f), ['the edge a → b passes through the box "x"'])
})

test('an edge along the border of a box does not pass through it', () => {
  const f = one(box('a', 0, 0, 20, 20) + box('x', 50, 10, 20, 20) + box('b', 100, 0, 20, 20) + edge('a', 'b', 'M20 10L100 10'))
  assert.deepEqual(geometryProblems(f), [])
})

test('an edge whose first or last point is not on the box it names is named', () => {
  const f = one(box('a', 0, 0, 20, 20) + box('b', 100, 0, 20, 20) + box('c', 200, 0, 20, 20) + edge('a', 'c', 'M20 10L100 10'))
  assert.deepEqual(geometryProblems(f), ['the edge a → c ends at (100, 10), not on the box "c"'])
  const g = one(box('a', 0, 0, 20, 20) + box('b', 100, 0, 20, 20) + box('c', 200, 0, 20, 20) + edge('b', 'c', 'M20 10L200 10'))
  assert.deepEqual(geometryProblems(g), ['the edge b → c starts at (20, 10), not on the box "b"'])
})

test('an edge whose end names no box is named', () => {
  const f = one(box('a', 0, 0, 20, 20) + edge('a', 'z', 'M20 10L100 10'))
  assert.deepEqual(geometryProblems(f), ['the edge a → z names the box "z", which the figure does not have'])
})

test('a link to another host and an image are found', () => {
  const f = one('<image href="https://example.org/i.svg"/>')
  assert.deepEqual(f.external, ['https://example.org/i.svg'])
  assert.equal(f.images, 1)
})
