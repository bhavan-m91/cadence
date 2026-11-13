import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { qk } from '../queryKeys'
import type { AuthEvent, ExportJob, Preferences, User } from '../types'
import { useAuthStore } from '@/stores/authStore'

export function usePreferences() {
  return useQuery({ queryKey: qk.preferences, queryFn: () => api.get<Preferences>('/users/me/preferences'), staleTime: 5 * 60_000 })
}

export function useUpdatePreferences() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (b: Partial<Preferences>) => api.patch<Preferences>('/users/me/preferences', b),
    onSuccess: (p) => {
      qc.setQueryData(qk.preferences, p)
      qc.invalidateQueries({ queryKey: ['timeline'] }); qc.invalidateQueries({ queryKey: ['analytics'] })
    },
  })
}

export function useUpdateProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (b: Partial<Pick<User, 'display_name' | 'role_title' | 'timezone' | 'theme'>>) => api.patch<User>('/users/me', b),
    onSuccess: (user) => {
      useAuthStore.getState().setUser(user)
      qc.invalidateQueries({ queryKey: ['timeline'] }); qc.invalidateQueries({ queryKey: ['analytics'] })
    },
  })
}

export function useAuthEvents() {
  return useQuery({ queryKey: qk.authEvents, queryFn: () => api.get<AuthEvent[]>('/users/me/auth-events', { limit: 15 }) })
}

export function useOnboarding() {
  return useMutation({
    mutationFn: (b: { timezone: string; seed: 'default' | 'empty'; ideal_day_preset: 'balanced' | 'none' }) =>
      api.post<{ categories_created: number; tags_created: number }>('/users/me/onboarding', b),
    onSuccess: async () => {
      useAuthStore.getState().setUser(await api.get<User>('/users/me'))
    },
  })
}

export const useRequestExport = () => useMutation({ mutationFn: () => api.post<ExportJob>('/users/me/exports') })

export function useExportJob(id: string | undefined) {
  return useQuery({
    queryKey: qk.exportJob(id ?? ''), enabled: !!id, queryFn: () => api.get<ExportJob>(`/exports/${id}`),
    refetchInterval: (q) => (q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 1500 : false),
  })
}

export const useDeleteAccount = () =>
  useMutation({ mutationFn: (b: { password: string; confirm: string }) => api.delete('/users/me', b) })
