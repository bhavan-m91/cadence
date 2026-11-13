import { create } from 'zustand'

export type ThemeMode = 'system' | 'light' | 'dark'
const KEY = 'cadence-theme'

function read(): ThemeMode {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

export const resolveTheme = (mode: ThemeMode): 'light' | 'dark' =>
  mode === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : mode

export function applyTheme(mode: ThemeMode) {
  document.documentElement.dataset.theme = resolveTheme(mode)
}

interface ThemeState {
  mode: ThemeMode
  resolved: 'light' | 'dark'
  setMode: (m: ThemeMode) => void
  toggle: () => ThemeMode
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  mode: read(),
  resolved: typeof matchMedia === 'undefined' ? 'light' : resolveTheme(read()),
  setMode: (mode) => {
    try {
      localStorage.setItem(KEY, mode)
    } catch {
      /* storage unavailable: theme still applies for this session */
    }
    applyTheme(mode)
    set({ mode, resolved: resolveTheme(mode) })
  },
  toggle: () => {
    const next: ThemeMode = get().resolved === 'dark' ? 'light' : 'dark'
    get().setMode(next)
    return next
  },
}))

if (typeof matchMedia !== 'undefined') {
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const { mode, setMode } = useThemeStore.getState()
    if (mode === 'system') setMode('system')
  })
}
