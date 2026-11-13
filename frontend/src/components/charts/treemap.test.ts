import { describe, expect, it } from 'vitest'
import { squarify } from './treemap'

describe('squarify', () => {
  it('fills the box exactly and sizes tiles in proportion to their value', () => {
    const rects = squarify([{ key: 'a', value: 60 }, { key: 'b', value: 30 }, { key: 'c', value: 10 }], 2)
    const area = (r: { w: number; h: number }) => r.w * r.h
    expect(rects.reduce((s, r) => s + area(r), 0)).toBeCloseTo(1, 6)
    const a = rects.find((r) => r.key === 'a')!, c = rects.find((r) => r.key === 'c')!
    expect(area(a) / area(c)).toBeCloseTo(6, 4)
  })

  it('keeps every tile inside the unit square and ignores empty values', () => {
    const rects = squarify([{ key: 'a', value: 5 }, { key: 'z', value: 0 }, { key: 'b', value: 3 }, { key: 'c', value: 2 }, { key: 'd', value: 1 }], 2.2)
    expect(rects.map((r) => r.key)).not.toContain('z')
    for (const r of rects) { expect(r.x).toBeGreaterThanOrEqual(-1e-9); expect(r.y).toBeGreaterThanOrEqual(-1e-9); expect(r.x + r.w).toBeLessThanOrEqual(1 + 1e-9); expect(r.y + r.h).toBeLessThanOrEqual(1 + 1e-9) }
  })

  it('returns nothing for no data', () => {
    expect(squarify([])).toEqual([])
    expect(squarify([{ key: 'a', value: 0 }])).toEqual([])
  })
})
