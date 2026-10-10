// The figures of a built page, read from its HTML, and the checks of their geometry.
//
// A figure is an `<svg role="img">`. Its boxes are the elements with a `data-box` attribute (a
// card or a panel, drawn as a `<rect>` with absolute `x`, `y`, `width` and `height`), and its
// edges are the `<path>` elements with a `data-edge` attribute, whose `data-from` and `data-to`
// name the boxes at the two ends. An edge's `d` holds absolute M, L, H, V and Q commands; the
// geometry takes the end point of each command, so a rounded corner counts as its chord.

/** The attributes of the start tag `tag`, as a map. */
function attributes(tag) {
  return new Map([...tag.matchAll(/([\w:-]+)="([^"]*)"/g)].map((m) => [m[1], m[2]]))
}

const unescape = (s) => s.replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&quot;', '"')
  .replaceAll('&#39;', "'").replaceAll('&amp;', '&')

/** The points of the path data `d`: the end point of each command. */
export function points(d) {
  const result = []
  let x = 0
  let y = 0
  for (const m of d.matchAll(/([MLHVQ])([^MLHVQ]*)/g)) {
    const n = m[2].trim().split(/[\s,]+/).filter(Boolean).map(Number)
    if (n.some(Number.isNaN)) throw new Error(`a path with data that is no number: ${d}`)
    if (m[1] === 'H') x = n[0]
    else if (m[1] === 'V') y = n[0]
    else [x, y] = n.slice(-2)
    result.push([x, y])
  }
  if (/[^MLHVQ\d\s,.-]/.test(d)) throw new Error(`a path with a command other than M, L, H, V and Q: ${d}`)
  return result
}

/** The figures of the HTML text `html`: their title, description, boxes and edges. */
export function figures(html) {
  const result = []
  // A figure's SVG holds nested <svg> elements (the icons), so a figure ends at the </svg> that
  // closes its own start tag: count the nesting.
  const open = /<svg\b[^>]*>|<\/svg>/g
  let depth = 0
  let start = -1
  let head = ''
  for (const m of html.matchAll(open)) {
    if (m[0].startsWith('</')) {
      if (depth === 0) continue
      depth--
      if (depth === 0 && start >= 0) {
        result.push(figure(head, html.slice(start, m.index)))
        start = -1
      }
    } else {
      if (depth === 0 && attributes(m[0]).get('role') === 'img') {
        start = m.index + m[0].length
        head = m[0]
      }
      if (depth > 0 || start >= 0) depth++
    }
  }
  return result
}

function figure(head, body) {
  const text = (tag) => {
    const m = new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)</${tag}>`).exec(body)
    return m ? unescape(m[1]).trim() : ''
  }
  const boxes = []
  for (const m of body.matchAll(/<rect\b[^>]*\bdata-box="[^"]*"[^>]*>/g)) {
    const a = attributes(m[0])
    boxes.push({
      name: unescape(a.get('data-box')),
      x: Number(a.get('x')), y: Number(a.get('y')), w: Number(a.get('width')), h: Number(a.get('height'))
    })
  }
  const edges = []
  for (const m of body.matchAll(/<path\b[^>]*\bdata-edge="[^"]*"[^>]*>/g)) {
    const a = attributes(m[0])
    // The label of an edge: the box behind its text, after the edge's path, before the next edge.
    const rest = body.slice(m.index + m[0].length)
    const next = rest.search(/\bdata-edge="/)
    const bg = /<rect\b[^>]*\bclass="fig-arrow-label-bg"[^>]*>/.exec(next < 0 ? rest : rest.slice(0, next))
    const l = bg && attributes(bg[0])
    edges.push({
      name: unescape(a.get('data-edge')), from: unescape(a.get('data-from') ?? ''),
      to: unescape(a.get('data-to') ?? ''), points: points(a.get('d') ?? ''),
      ...(l ? { label: { x: Number(l.get('x')), y: Number(l.get('y')), w: Number(l.get('width')), h: Number(l.get('height')) } } : {})
    })
  }
  return {
    head, title: text('title'), desc: text('desc'), boxes, edges,
    external: [...body.matchAll(/\b(?:href|src)="([^"]*)"/g)].map((m) => m[1]).filter((u) => /^(?:https?:)?\/\//.test(u)),
    images: (body.match(/<(?:img|image|foreignObject)\b/g) ?? []).length,
    // The whole markup of the figure, and the text of its <style> elements.
    svg: `${head}${body}</svg>`,
    style: [...body.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/g)].map((m) => m[1]).join('\n')
  }
}

const NAME = '[A-Za-z_:][\\w:.-]*'
const START = new RegExp(`^<(${NAME})((?:\\s+${NAME}\\s*=\\s*(?:"[^"<]*"|'[^'<]*'))*)\\s*(/?)>$`)
const ENTITY = /&(?!(?:lt|gt|amp|quot|apos|#[0-9]+|#x[0-9a-fA-F]+);)/

/** The first problem of the XML text `text`, or none: each start tag is well-formed, with each
 * attribute once and quoted; each element closes in order; an `&` starts an entity; and one root
 * element holds everything but comments and white space. The markup of a figure has no DTD, no
 * CDATA section and no processing instruction, so a `<!` other than a comment is a problem. */
export function xmlProblems(text) {
  const stack = []
  let rooted = false
  for (const m of text.matchAll(/<!--[\s\S]*?-->|<[^>]*>?|[^<]+/g)) {
    const token = m[0]
    if (token.startsWith('<!--')) continue
    if (!token.startsWith('<')) {
      if (ENTITY.test(token)) return ['a & that starts no entity']
      if (stack.length === 0 && token.trim() !== '') return [rooted ? 'text or an element after the root element' : 'text before the root element']
      continue
    }
    const end = /^<\/([^\s>]+)\s*>$/.exec(token)
    if (end) {
      const open = stack.pop()
      if (open === undefined) return [`the end tag ${token} closes no element`]
      if (open !== end[1]) return [`the element <${open}> closes with ${token}`]
      if (stack.length === 0) rooted = true
      continue
    }
    const start = START.exec(token)
    if (!start) return [`the start tag ${token} is not well-formed`]
    if (stack.length === 0 && rooted) return ['text or an element after the root element']
    const names = [...start[2].matchAll(new RegExp(`(${NAME})\\s*=\\s*("[^"<]*"|'[^'<]*')`, 'g'))]
    const seen = new Set()
    for (const [, name, value] of names) {
      if (seen.has(name)) return [`the start tag <${start[1]}> has the attribute ${name} twice`]
      seen.add(name)
      if (ENTITY.test(value)) return ['a & that starts no entity']
    }
    if (start[3] === '/') {
      if (stack.length === 0) rooted = true
    } else stack.push(start[1])
  }
  if (stack.length > 0) return [`the element <${stack.at(-1)}> is not closed`]
  return rooted ? [] : ['no root element']
}

/** The top-level blocks of the CSS text `css`: each its prelude and the text between its braces. */
function blocks(css) {
  const result = []
  let depth = 0
  let start = 0
  let prelude = ''
  const text = css.replace(/\/\*[\s\S]*?\*\//g, '')
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '{') {
      if (depth === 0) {
        prelude = text.slice(start, i).trim()
        start = i + 1
      }
      depth++
    } else if (text[i] === '}') {
      depth--
      if (depth === 0) {
        result.push({ prelude, body: text.slice(start, i) })
        start = i + 1
      }
    }
  }
  return result
}

/** The declarations of a CSS block, by property. */
const declarations = (body) => new Map(body.split(';').map((d) => d.split(/:(.*)/s))
  .filter((p) => p.length > 1).map(([k, v]) => [k.trim(), v.trim()]))

/** The rules of the CSS text `css`: the selectors, each by its last compound, and the
 * declarations; the @media blocks with their rules; and the @keyframes with their stops. */
function stylesheet(css) {
  const rules = (text) => blocks(text).filter((b) => !b.prelude.startsWith('@'))
    .map((b) => ({ last: b.prelude.split(',').map((s) => s.trim().split(/\s+/).at(-1)), decls: declarations(b.body) }))
  const all = blocks(css)
  return {
    rules: rules(css),
    media: all.filter((b) => b.prelude.startsWith('@media')).map((b) => ({ query: b.prelude, rules: rules(b.body) })),
    keyframes: new Map(all.filter((b) => b.prelude.startsWith('@keyframes')).map((b) => [
      b.prelude.replace('@keyframes', '').trim(),
      blocks(b.body).flatMap((s) => s.prelude.split(',').map((p) => ({
        at: p.trim() === 'from' ? 0 : p.trim() === 'to' ? 100 : Number.parseFloat(p), decls: declarations(s.body)
      }))).sort((a, b) => a.at - b.at)
    ]))
  }
}

/** The bounds of the timing of the walk-throughs, after the user's example: a token moves along
 * an edge for 0.5–0.8 s, and the animation holds each step for at least 1.2 s. */
export const TRAVEL = [0.5, 0.8]
export const HOLD = 1.2

const seconds = (s) => Number(s.toFixed(2))

/** The problems of an animated figure, a walk-through. Its markup parses as XML and holds no
 * <script>, no SMIL element and no URL of another host. Its <style> loops the animation of every
 * element of the class wt-anim; under prefers-reduced-motion it runs no animation, shows every box
 * of the class wt-box unfaded and hides each token of the class wt-token. Each animation name has
 * its @keyframes, and each @keyframes is used. A token is visible (opacity 1) while it moves: each
 * such run lasts 0.5–0.8 s, and the time from one run to the next, the hold of a step, at least
 * 1.2 s. */
export function animationProblems(fig) {
  const problems = []
  const xml = xmlProblems(fig.svg)
  if (xml.length > 0) problems.push(`does not parse as XML: ${xml[0]}`)
  if (/<script\b/i.test(fig.svg)) problems.push('holds a <script>')
  for (const m of fig.svg.matchAll(/<(animate|animateMotion|animateTransform|animateColor|set)\b/g)) problems.push(`holds the SMIL element <${m[1]}>`)
  for (const m of fig.style.matchAll(/(?:url\(|@import)\s*['"]?((?:https?:)?\/\/[^'")\s;]*)/g)) problems.push(`loads ${m[1]} from another host`)
  const css = stylesheet(fig.style)
  const has = (rules, cls, prop, value) => rules.some((r) => r.last.includes(cls) && r.decls.get(prop) === value)
  const reduced = css.media.find((m) => /prefers-reduced-motion\s*:\s*reduce/.test(m.query))
  if (!reduced) problems.push('has no @media (prefers-reduced-motion: reduce) block')
  else {
    if (!has(reduced.rules, '.wt-anim', 'animation', 'none')) problems.push('runs an animation under prefers-reduced-motion: no rule .wt-anim { animation: none }')
    if (!has(reduced.rules, '.wt-box', 'opacity', '1')) problems.push('fades a box under prefers-reduced-motion: no rule .wt-box { opacity: 1 }')
    if (!has(reduced.rules, '.wt-token', 'display', 'none')) problems.push('shows the token under prefers-reduced-motion: no rule .wt-token { display: none }')
  }
  if (!has(css.rules, '.wt-anim', 'animation-iteration-count', 'infinite')) problems.push('does not loop: no rule .wt-anim { animation-iteration-count: infinite }')
  const used = new Set(css.rules.flatMap((r) => (r.decls.get('animation-name') ?? '').split(',').map((n) => n.trim()).filter(Boolean)))
  for (const name of used) if (!css.keyframes.has(name)) problems.push(`the animation ${name} has no @keyframes`)
  for (const name of css.keyframes.keys()) if (!used.has(name)) problems.push(`the @keyframes ${name} is not used`)
  if (!/<[^>]*\bclass="[^"]*\bwt-token\b/.test(fig.svg)) {
    problems.push('has no token')
    return problems
  }
  const duration = css.rules.filter((r) => r.last.includes('.wt-anim')).map((r) => Number.parseFloat(r.decls.get('animation-duration') ?? ''))
    .find((d) => !Number.isNaN(d))
  if (duration === undefined) {
    problems.push('has no rule .wt-anim { animation-duration }')
    return problems
  }
  // The runs of each token: the stops in a row at which it is visible.
  const runs = []
  for (const [name, stops] of css.keyframes) {
    if (!stops.some((s) => s.decls.has('offset-distance'))) continue
    let run = null
    for (const s of stops) {
      if (s.decls.get('opacity') === '1') run ??= { name, from: s.at }
      if (run && s.decls.get('opacity') === '1') run.to = s.at
      if (run && s.decls.get('opacity') !== '1') {
        runs.push(run)
        run = null
      }
    }
    if (run) runs.push(run)
  }
  runs.sort((a, b) => a.from - b.from)
  for (const r of runs) {
    const t = ((r.to - r.from) * duration) / 100
    if (t < TRAVEL[0] - 1e-6 || t > TRAVEL[1] + 1e-6) problems.push(`the token of ${r.name} moves for ${seconds(t)} s, not ${TRAVEL[0]}–${TRAVEL[1]} s`)
  }
  for (const [i, r] of runs.entries()) {
    const next = runs[(i + 1) % runs.length]
    // The next run starts after this one, or in the next cycle.
    const hold = (((next.from - r.to + 100) % 100) * duration) / 100
    if (hold < HOLD - 1e-6) problems.push(`the step after ${r.name} holds for ${seconds(hold)} s, less than ${HOLD} s`)
  }
  return problems
}

const EPS = 0.5

/** The points where the segments [p, q] and [r, s] meet: none, one, or the two ends of their
 * common part when they lie on one line. */
export function meet([p, q], [r, s]) {
  const d = (a, b) => [b[0] - a[0], b[1] - a[1]]
  const cross = (a, b) => a[0] * b[1] - a[1] * b[0]
  const u = d(p, q)
  const v = d(r, s)
  const w = d(p, r)
  const den = cross(u, v)
  if (Math.abs(den) < 1e-9) {
    if (Math.abs(cross(u, w)) > 1e-6 * Math.max(1, Math.hypot(...u))) return []
    // On one line: project onto the longer axis.
    const axis = Math.abs(u[0]) + Math.abs(v[0]) >= Math.abs(u[1]) + Math.abs(v[1]) ? 0 : 1
    const lo = Math.max(Math.min(p[axis], q[axis]), Math.min(r[axis], s[axis]))
    const hi = Math.min(Math.max(p[axis], q[axis]), Math.max(r[axis], s[axis]))
    if (lo > hi + EPS) return []
    const at = (t) => {
      const [a, b] = Math.abs(q[axis] - p[axis]) > 1e-9 ? [p, q] : [r, s]
      if (Math.abs(b[axis] - a[axis]) < 1e-9) return [...a]
      const k = (t - a[axis]) / (b[axis] - a[axis])
      return [a[0] + k * (b[0] - a[0]), a[1] + k * (b[1] - a[1])]
    }
    return [at(lo), at(hi)]
  }
  const t = cross(w, v) / den
  const k = cross(w, u) / den
  const tol = (seg) => EPS / Math.max(1e-9, Math.hypot(...seg))
  if (t < -tol(u) || t > 1 + tol(u) || k < -tol(v) || k > 1 + tol(v)) return []
  return [[p[0] + t * u[0], p[1] + t * u[1]]]
}

const inside = (pt, b, pad = EPS) => pt[0] >= b.x - pad && pt[0] <= b.x + b.w + pad && pt[1] >= b.y - pad && pt[1] <= b.y + b.h + pad
const contains = (outer, b) => b.x >= outer.x - EPS && b.y >= outer.y - EPS &&
  b.x + b.w <= outer.x + outer.w + EPS && b.y + b.h <= outer.y + outer.h + EPS

/** Whether the segment [p, q] passes through the inside of the box `b`, its border excluded. */
function through([p, q], b) {
  // Clip the segment to the box shrunk by 1 (Liang-Barsky).
  const x0 = b.x + 1
  const y0 = b.y + 1
  const x1 = b.x + b.w - 1
  const y1 = b.y + b.h - 1
  if (x1 <= x0 || y1 <= y0) return false
  let lo = 0
  let hi = 1
  const dx = q[0] - p[0]
  const dy = q[1] - p[1]
  for (const [pp, qq] of [[-dx, p[0] - x0], [dx, x1 - p[0]], [-dy, p[1] - y0], [dy, y1 - p[1]]]) {
    if (pp === 0) {
      if (qq <= 0) return false
    } else {
      const r = qq / pp
      if (pp < 0) lo = Math.max(lo, r)
      else hi = Math.min(hi, r)
    }
  }
  return hi - lo > 1e-9
}

const segments = (e) => e.points.slice(1).map((pt, i) => [e.points[i], pt])
const at = ([x, y]) => `(${Math.round(x)}, ${Math.round(y)})`

/** The length of the path `pts` from its first point to the point `pt` on it, or NaN. */
function along(pts, pt) {
  let s = 0
  for (let i = 1; i < pts.length; i++) {
    const [p, q] = [pts[i - 1], pts[i]]
    const len = Math.hypot(q[0] - p[0], q[1] - p[1])
    const t = len === 0 ? 0 : ((pt[0] - p[0]) * (q[0] - p[0]) + (pt[1] - p[1]) * (q[1] - p[1])) / len ** 2
    const k = Math.min(1, Math.max(0, t))
    if (Math.hypot(p[0] + k * (q[0] - p[0]) - pt[0], p[1] + k * (q[1] - p[1]) - pt[1]) <= EPS) return s + k * len
    s += len
  }
  return NaN
}

/** Whether the point `pt`, where the edges `a` and `b` meet, is on a trunk that they share: both
 * leave one box, or both enter one box, along the same path up to `pt`. Two such edges merge
 * there; they do not cross. */
function trunk(a, b, pt) {
  const same = (pa, pb) => Math.abs(along(pa, pt) - along(pb, pt)) <= 2 * EPS &&
    Math.hypot(pa[0][0] - pb[0][0], pa[0][1] - pb[0][1]) <= EPS
  return (a.from === b.from && same(a.points, b.points)) ||
    (a.to === b.to && same([...a.points].reverse(), [...b.points].reverse()))
}

/** The problems of a figure's geometry: an edge whose end names no box or does not lie on the box
 * that it names, two edges that meet
 * outside a box at an end of both and off a trunk that they share, and an edge that passes
 * through a box that is neither one of its ends nor a box around one of them. */
export function geometryProblems(fig) {
  const problems = []
  const byName = new Map(fig.boxes.map((b) => [b.name, b]))
  for (const e of fig.edges) {
    for (const end of [e.from, e.to]) {
      if (!byName.has(end)) problems.push(`the edge ${e.name} names the box "${end}", which the figure does not have`)
    }
    if (e.points.length < 2) problems.push(`the edge ${e.name} has fewer than two points`)
  }
  if (problems.length > 0) return problems
  // An edge starts on the box that it names as its start and ends on the box that it names as its
  // end, so that the names that the checks below trust are true.
  for (const e of fig.edges) {
    const [first, last] = [e.points[0], e.points.at(-1)]
    if (!inside(first, byName.get(e.from))) problems.push(`the edge ${e.name} starts at ${at(first)}, not on the box "${e.from}"`)
    if (!inside(last, byName.get(e.to))) problems.push(`the edge ${e.name} ends at ${at(last)}, not on the box "${e.to}"`)
  }
  const ends = (e) => [byName.get(e.from), byName.get(e.to)]
  for (const [i, a] of fig.edges.entries()) {
    for (const b of fig.edges.slice(i + 1)) {
      const shared = ends(a).filter((x) => ends(b).includes(x))
      let found = null
      for (const sa of segments(a)) {
        for (const sb of segments(b)) {
          for (const pt of meet(sa, sb)) {
            if (!shared.some((box) => inside(pt, box)) && !trunk(a, b, pt)) found ??= pt
          }
        }
      }
      if (found) problems.push(`the edges ${a.name} and ${b.name} cross at ${at(found)}`)
    }
  }
  for (const e of fig.edges) {
    const own = ends(e)
    for (const box of fig.boxes) {
      if (own.includes(box) || own.some((end) => contains(box, end))) continue
      if (segments(e).some((s) => through(s, box))) problems.push(`the edge ${e.name} passes through the box "${box.name}"`)
    }
  }
  return problems
}

/** Whether the segments `s` and `t` lie on one line and share a part longer than EPS: two edges
 * on a trunk that they share. */
function shared(s, t) {
  const m = meet(s, t)
  return m.length === 2 && Math.hypot(m[0][0] - m[1][0], m[0][1] - m[1][1]) > EPS
}

/** The problems of the labels of a figure's edges. A label sits on its own edge: the edge passes
 * through the centre of the label's box. No other edge passes through the box, so that no other
 * edge is as near the label as its own; a part of another edge on a trunk that it shares with the
 * label's edge does not count. And no two labels overlap. */
export function labelProblems(fig) {
  const problems = []
  const labelled = fig.edges.filter((e) => e.label)
  for (const e of labelled) {
    const b = e.label
    const centre = [b.x + b.w / 2, b.y + b.h / 2]
    if (!segments(e).some((s) => meet(s, [centre, centre]).length > 0)) {
      problems.push(`the label of the edge ${e.name} is not on its own edge`)
      continue
    }
    const own = segments(e)
    for (const f of fig.edges) {
      if (f === e) continue
      const near = segments(f).filter((s) => !own.some((t) => shared(s, t))).some((s) => through(s, b))
      if (near) problems.push(`the label of the edge ${e.name} is as near the edge ${f.name} as its own`)
    }
  }
  for (const [i, e] of labelled.entries()) {
    for (const f of labelled.slice(i + 1)) {
      const [a, b] = [e.label, f.label]
      if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h) {
        problems.push(`the labels of the edges ${e.name} and ${f.name} overlap`)
      }
    }
  }
  return problems
}

/** The width of the viewBox of a figure, or NaN when it has none. The HTML of the build writes the
 * attribute in lower case. */
export function figureWidth(fig) {
  const m = /\bviewBox="([^"]*)"/i.exec(fig.head)
  return m ? Number(m[1].trim().split(/[\s,]+/)[2]) : NaN
}

/** The problem of a figure that is wider than `max` px, or null. A figure whose title `exempt`
 * names has no width rule; the exemption is by title only. */
export function widthProblem(fig, max, exempt = []) {
  if (exempt.includes(fig.title)) return null
  const width = figureWidth(fig)
  return width <= max ? null : `is ${width} px wide, more than ${max} px`
}

/** The problems of the layers of a graph: the boxes of one layer have one width and share one
 * edge line. The edges give the direction: a graph whose edges leave their boxes at the bottom
 * runs downwards, and its layers are rows that share the top edge; a graph whose edges leave on
 * the right runs to the right, and its layers are columns that share the left edge. A layer is a
 * set of boxes whose extents along the direction overlap. */
export function layerProblems(fig) {
  const byName = new Map(fig.boxes.map((b) => [b.name, b]))
  const sides = new Set(fig.edges.map((e) => {
    const b = byName.get(e.from)
    const [x, y] = e.points[0]
    if (b && Math.abs(y - (b.y + b.h)) <= EPS) return 'bottom'
    if (b && Math.abs(x - (b.x + b.w)) <= EPS) return 'right'
    return 'other'
  }))
  if (sides.size === 0) return []
  if (sides.size > 1 || sides.has('other')) return ['the edges leave their boxes on different sides, so the graph has no one direction']
  const [kind, start, size, line] = sides.has('bottom') ? ['row', 'y', 'h', 'top edges'] : ['column', 'x', 'w', 'left edges']
  const sorted = [...fig.boxes].sort((a, b) => a[start] - b[start])
  const layers = []
  for (const b of sorted) {
    const last = layers.at(-1)
    if (last && b[start] < Math.max(...last.map((c) => c[start] + c[size])) - EPS) last.push(b)
    else layers.push([b])
  }
  const problems = []
  const distinct = (values) => [...new Set(values)].sort((a, b) => a - b)
  for (const layer of layers.filter((l) => l.length > 1)) {
    const name = `the ${kind} of ${layer.map((b) => b.name).sort().join(', ')}`
    const widths = distinct(layer.map((b) => b.w))
    if (widths.length > 1) problems.push(`${name}: the boxes have the widths ${widths.join(', ')}, not one width`)
    const edges = distinct(layer.map((b) => b[start]))
    if (edges.length > 1) problems.push(`${name}: the boxes have the ${line} ${edges.join(', ')}, not one`)
  }
  return problems
}
