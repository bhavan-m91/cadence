import { api, refreshSession } from './client'
import type { User } from './types'
import { useAuthStore } from '@/stores/authStore'
import { applyTheme, useThemeStore } from '@/stores/themeStore'

/** On load: trade the refresh cookie for an access token, then fetch the profile (PRD 8.2). */
export async function bootstrapSession(): Promise<void> {
  const store = useAuthStore.getState()
  if (!(await refreshSession())) return store.clear()
  try {
    const user = await api.get<User>('/users/me')
    syncTheme(user)
    store.setSession(useAuthStore.getState().accessToken!, user)
  } catch {
    store.clear()
  }
}

export function syncTheme(user: User) {
  const t = useThemeStore.getState()
  // The profile theme is the source of truth across devices; 'system' follows the OS.
  if (user.theme !== t.mode) {
    t.setMode(user.theme)
  } else {
    applyTheme(t.mode)
  }
}
