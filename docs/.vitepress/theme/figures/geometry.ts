// The sizes of the figure components, and the width of a text, for the layouts of the figures.
// The build has no browser to measure a text, so `textWidth` sums a width for each character: the
// widths of Helvetica, in thousandths of the font size, made 8 % wider for Inter. A text that is
// wider than the estimate still fits, because the cards have room to spare on the right.

/** The height of a card with no grey line, one grey line and two grey lines. */
export const CARD_HEIGHT = [52, 60, 72]
/** The side of the tinted square behind a card's icon, and the gaps around it. */
export const ICON_BOX = 32
export const CARD_PAD = 10
/** The font sizes of a card's title and grey lines, and of an arrow's label. */
export const TITLE_SIZE = 13.5
export const LINE_SIZE = 11.5
export const LABEL_SIZE = 11
/** The height of a panel's header band. */
export const BAND = 40

// Helvetica's widths of the characters from ' ' (32) to '~' (126).
const WIDTHS = [
  278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
  556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
  1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
  667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
  333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
  556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584
]

/** The width of `text` at `size` pixels; `bold` adds 7 %, and `mono` gives each character 0.6 of
 * the size. */
export function textWidth(text: string, size: number, bold = false, mono = false): number {
  if (mono) return [...text].length * 0.6 * size
  let units = 0
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0
    units += code >= 32 && code <= 126 ? WIDTHS[code - 32] : 600
  }
  return (units / 1000) * size * 1.08 * (bold ? 1.07 : 1)
}

/** The width of a card that holds `title` and the grey `lines`. */
export function cardWidth(title: string, lines: string[] = [], mono = false): number {
  const text = Math.max(textWidth(title, TITLE_SIZE, true, mono), ...lines.map((l) => textWidth(l, LINE_SIZE)))
  return Math.ceil(CARD_PAD + ICON_BOX + CARD_PAD + text + 14)
}

/** The height of a card with `n` grey lines. */
export const cardHeight = (n: number) => CARD_HEIGHT[Math.min(n, 2)]

/** A point of a figure. */
export type Point = [number, number]

/** The SVG path of the polyline `points`, with each corner rounded by `radius` at most. Only M, L
 * and Q commands, which the check of the built site reads (docs/scripts/figures.mjs). */
export function roundedPath(points: Point[], radius = 6): string {
  const f = (n: number) => String(Math.round(n * 10) / 10)
  const p = (pt: Point) => `${f(pt[0])} ${f(pt[1])}`
  let d = `M${p(points[0])}`
  for (let i = 1; i < points.length - 1; i++) {
    const [a, b, c] = [points[i - 1], points[i], points[i + 1]]
    const r = Math.min(radius, Math.hypot(b[0] - a[0], b[1] - a[1]) / 2, Math.hypot(c[0] - b[0], c[1] - b[1]) / 2)
    const towards = (from: Point, to: Point, k: number): Point => {
      const len = Math.hypot(to[0] - from[0], to[1] - from[1]) || 1
      return [from[0] + ((to[0] - from[0]) / len) * k, from[1] + ((to[1] - from[1]) / len) * k]
    }
    d += `L${p(towards(b, a, r))}Q${p(b)} ${p(towards(b, c, r))}`
  }
  return d + `L${p(points[points.length - 1])}`
}
