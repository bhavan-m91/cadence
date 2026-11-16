import { create } from 'zustand'

/** The Work / Personal lens: one switch that narrows Overview, Calendar and the Ideal editor to one side of life. Remembered per browser. */
export type Lens = 'all' | 'work' | 'personal'
const KEY = 'cadence-lens'

function read(): Lens {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'work' || v === 'personal' ? v : 'all'
  } catch {
    return 'all'
  }
}

interface LensState { lens: Lens; setLens: (l: Lens) => void }

export const useLensStore = create<LensState>((set) => ({
  lens: read(),
  setLens: (lens) => {
    try { localStorage.setItem(KEY, lens) } catch { /* private window: the choice simply lasts for this visit */ }
    set({ lens })
  },
}))

/** Which category roots a lens shows. Sleep belongs to personal life. */
export const LENS_ROOTS: Record<Lens, string[] | null> = { all: null, work: ['work'], personal: ['personal', 'sleep'] }
export const inLens = (lens: Lens, rootKind: string) => LENS_ROOTS[lens]?.includes(rootKind) ?? true
