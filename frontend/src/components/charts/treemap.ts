/** Squarified treemap (Bruls, Huizing, van Wijk). Pure: sizes in, rectangles out, in 0..1 coordinates. */
export interface TreeInput { key: string; value: number }
export interface TreeRect { key: string; value: number; x: number; y: number; w: number; h: number }

function worst(row: number[], side: number): number {
  const s = row.reduce((a, b) => a + b, 0)
  if (s === 0 || side === 0) return Infinity
  const max = Math.max(...row), min = Math.min(...row)
  return Math.max((side * side * max) / (s * s), (s * s) / (side * side * min))
}

export function squarify(items: TreeInput[], aspect = 1): TreeRect[] {
  const list = items.filter((i) => i.value > 0).sort((a, b) => b.value - a.value)
  const total = list.reduce((a, i) => a + i.value, 0)
  if (!total) return []
  // Work in a box of width `aspect` and height 1 so tiles are squarish on screen, then normalise back to 0..1.
  const area = aspect
  const scaled = list.map((i) => ({ ...i, a: (i.value / total) * area }))
  const out: TreeRect[] = []
  let x = 0, y = 0, w = aspect, h = 1
  let row: typeof scaled = []
  const layoutRow = (r: typeof scaled) => {
    const sum = r.reduce((a, i) => a + i.a, 0)
    if (w >= h) {
      const rw = sum / h
      let cy = y
      for (const i of r) { const ih = i.a / rw; out.push({ key: i.key, value: i.value, x, y: cy, w: rw, h: ih }); cy += ih }
      x += rw; w -= rw
    } else {
      const rh = sum / w
      let cx = x
      for (const i of r) { const iw = i.a / rh; out.push({ key: i.key, value: i.value, x: cx, y, w: iw, h: rh }); cx += iw }
      y += rh; h -= rh
    }
  }
  for (const item of scaled) {
    const side = Math.min(w, h)
    if (row.length === 0 || worst([...row, item].map((i) => i.a), side) <= worst(row.map((i) => i.a), side)) row.push(item)
    else { layoutRow(row); row = [item] }
  }
  if (row.length) layoutRow(row)
  return out.map((r) => ({ ...r, x: r.x / aspect, w: r.w / aspect }))
}
