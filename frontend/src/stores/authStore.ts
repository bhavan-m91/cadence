import { create } from 'zustand'
import type { User } from '@/api/types'

type Status = 'loading' | 'authed' | 'anon'

interface AuthState {
  status: Status
  /** Access token lives in memory only (FR-005). */
  accessToken: string | null
  user: User | null
  setSession: (token: string, user?: User | null) => void
  setToken: (token: string) => void
  setUser: (user: User) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  status: 'loading',
  accessToken: null,
  user: null,
  setSession: (accessToken, user = null) => set((s) => ({ status: 'authed', accessToken, user: user ?? s.user })),
  setToken: (accessToken) => set({ accessToken }),
  setUser: (user) => set({ user }),
  clear: () => set({ status: 'anon', accessToken: null, user: null }),
}))
