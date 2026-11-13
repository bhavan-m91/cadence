import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, request } from '../client'
import type { User } from '../types'
import { syncTheme } from '../session'
import { useAuthStore } from '@/stores/authStore'

interface AuthOut { access_token: string; expires_in: number; user: User }

function adopt(out: AuthOut) {
  syncTheme(out.user)
  useAuthStore.getState().setSession(out.access_token, out.user)
}

export function useLogin() {
  return useMutation({
    mutationFn: (b: { email: string; password: string; remember: boolean }) => api.post<AuthOut>('/auth/login', b, { auth: false }),
    onSuccess: adopt,
  })
}

export function useRegister() {
  return useMutation({
    mutationFn: (b: { email: string; password: string; display_name: string; timezone: string }) => api.post<AuthOut>('/auth/register', b, { auth: false }),
    onSuccess: adopt,
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (all: boolean = false) => request('/auth/logout', { method: 'POST', body: { all } }),
    onSettled: () => {
      useAuthStore.getState().clear()
      qc.clear()
    },
  })
}

export const useForgotPassword = () => useMutation({ mutationFn: (email: string) => api.post('/auth/password/forgot', { email }, { auth: false }) })
export const useResetPassword = () => useMutation({ mutationFn: (b: { token: string; password: string }) => api.post('/auth/password/reset', b, { auth: false }) })
export const useVerifyEmail = () => useMutation({ mutationFn: (token: string) => api.post('/auth/verify-email', { token }, { auth: false }) })
export const useResendVerification = () => useMutation({ mutationFn: () => api.post('/auth/resend-verification') })
export const useChangePassword = () => useMutation({ mutationFn: (b: { current_password: string; new_password: string }) => api.post('/auth/password/change', b) })
