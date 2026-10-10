// Cases of scripts/figures.mjs, the reader of a built figure and its geometry checks. Run with
// `node --test scripts/`, which `npm run docs:check` does first.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { figureWidth, figures, geometryProblems, labelProblems, layerProblems, meet, points, widthProblem } from './figures.mjs'

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

test('the width of a figure is the width of its viewBox, in either case of the attribute', () => {
  assert.equal(figureWidth(one(box('a', 0, 0, 10, 10))), 400)
  assert.equal(figureWidth(figures('<svg role="img" viewbox="-12 -12 765.5 300"><title>T</title></svg>')[0]), 765.5)
  assert.ok(Number.isNaN(figureWidth(figures('<svg role="img"><title>T</title></svg>')[0])))
})

test('a figure wider than the limit is a problem, unless its title is exempt by name', () => {
  const wide = (title) => figures(`<svg role="img" viewbox="-12 -12 1171 300"><title>${title}</title></svg>`)[0]
  assert.equal(widthProblem(wide('Every spawn'), 765, ['Every spawn']), null)
  assert.equal(widthProblem(wide('The calls of build-part'), 765, ['Every spawn']), 'is 1171 px wide, more than 765 px')
  assert.equal(widthProblem(wide('Every spawn of a part'), 765, ['Every spawn']), 'is 1171 px wide, more than 765 px')
  assert.equal(widthProblem(figures('<svg role="img" viewbox="0 0 765 300"><title>T</title></svg>')[0], 765), null)
  assert.equal(widthProblem(figures('<svg role="img"><title>T</title></svg>')[0], 765), 'is NaN px wide, more than 765 px')
})

// A graph that runs downwards: a, then the row of b, c and d.
const down = (c = [140, 'c'], d = 'd') =>
  box('a', 0, 0, 100, 40) + box('b', 0, 100, 100, 40) + box('c', c[0], 100, 100, 40) + box(d, 280, 100, 100, 40) +
  edge('a', 'b', 'M50 40L50 100') + edge('a', 'c', 'M50 40L50 70L190 70L190 100')

test('the boxes of each row of a graph that runs downwards share their width and their top edge', () => {
  assert.deepEqual(layerProblems(one(down())), [])
  assert.deepEqual(layerProblems(one(down().replace('box="c" x="140" y="100" width="100"', 'box="c" x="140" y="100" width="130"'))),
    ['the row of b, c, d: the boxes have the widths 100, 130, not one width'])
  assert.deepEqual(layerProblems(one(down().replace('box="d" x="280" y="100"', 'box="d" x="280" y="110"'))),
    ['the row of b, c, d: the boxes have the top edges 100, 110, not one'])
})

test('the boxes of each column of a graph that runs to the right share their width and their left edge', () => {
  const right = (w) => box('a', 0, 0, 100, 40) + box('b', 200, 0, w, 40) + box('c', 200, 60, 120, 40) +
    edge('a', 'b', 'M100 20L200 20') + edge('a', 'c', 'M100 20L150 20L150 80L200 80')
  assert.deepEqual(layerProblems(one(right(120))), [])
  assert.deepEqual(layerProblems(one(right(100))), ['the column of b, c: the boxes have the widths 100, 120, not one width'])
})

test('a graph whose edges leave their boxes on different sides has no direction', () => {
  const f = one(box('a', 0, 0, 100, 40) + box('b', 0, 100, 100, 40) + box('c', 200, 0, 100, 40) +
    edge('a', 'b', 'M50 40L50 100') + edge('a', 'c', 'M100 20L200 20'))
  assert.deepEqual(layerProblems(f), ['the edges leave their boxes on different sides, so the graph has no one direction'])
})

// An arrow with a label, as FigArrow draws it: the path, the head, and the label's box.
const labelled = (from, to, d, [x, y, w, h]) =>
  `<g class="fig-arrow"><path class="fig-arrow-line" data-edge="${from} → ${to}" data-from="${from}" data-to="${to}" d="${d}"/>` +
  `<path class="fig-arrow-head" d="M0 0Z"/><rect class="fig-arrow-label-bg" x="${x}" y="${y}" width="${w}" height="${h}"/></g>`
// a calls b and c downwards; the two edges part at y = 60 and run down at x = 50 and x = 250.
const pair = (bLabel, cLabel) => one(box('a', 0, 0, 300, 40) + box('b', 0, 160, 100, 40) + box('c', 200, 160, 100, 40) +
  labelled('a', 'b', 'M150 40L150 60L50 60L50 160', bLabel) + labelled('a', 'c', 'M150 40L150 60L250 60L250 160', cLabel))

test('the label of each edge is read with its box', () => {
  const f = pair([10, 100, 80, 18], [210, 100, 80, 18])
  assert.deepEqual(f.edges.map((e) => e.label), [{ x: 10, y: 100, w: 80, h: 18 }, { x: 210, y: 100, w: 80, h: 18 }])
})

test('a label centred on its own edge, with no other edge through it, passes', () => {
  assert.deepEqual(labelProblems(pair([10, 100, 80, 18], [210, 100, 80, 18])), [])
})

test('a label beside its edge, in the band between two edges, is named', () => {
  // The label of a → c sits left of its edge, between the two edges: nearer a → b than its own.
  assert.deepEqual(labelProblems(pair([10, 100, 80, 18], [100, 100, 120, 18])),
    ['the label of the edge a → c is not on its own edge'])
})

test('a label that another edge passes through is named, and one on a shared trunk is not', () => {
  // The label of a → b is on its edge at the trunk (x = 150, y 40–60), which a → c shares.
  assert.deepEqual(labelProblems(pair([110, 41, 80, 18], [210, 100, 80, 18])), [])
  // A wide label of a → b at x = 50 reaches the edge a → c at x = 250.
  assert.deepEqual(labelProblems(pair([-160, 100, 420, 18], [210, 130, 80, 18])),
    ['the label of the edge a → b is as near the edge a → c as its own'])
})

test('two labels that overlap are named', () => {
  // The edges run down at x = 50 and x = 250; the labels are on them but wide enough to meet.
  const f = pair([-50, 100, 200, 18], [140, 110, 220, 18])
  assert.ok(labelProblems(f).includes('the labels of the edges a → b and a → c overlap'), labelProblems(f).join('; '))
})

test('a link to another host and an image are found', () => {
  const f = one('<image href="https://example.org/i.svg"/>')
  assert.deepEqual(f.external, ['https://example.org/i.svg'])
  assert.equal(f.images, 1)
})
