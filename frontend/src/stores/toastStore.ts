import { create } from 'zustand'

export interface Toast {
  id: number
  kind: 'info' | 'success' | 'error'
  message: string
  action?: { label: string; run: () => void }
}

interface ToastState {
  toasts: Toast[]
  push: (t: Omit<Toast, 'id'>, ttl?: number) => number
  dismiss: (id: number) => void
}

let next = 1

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  push: (t, ttl = 5000) => {
    const id = next++
    set((s) => ({ toasts: [...s.toasts, { ...t, id }] }))
    if (ttl > 0) setTimeout(() => get().dismiss(id), ttl)
    return id
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}))

export const toast = {
  info: (message: string) => useToastStore.getState().push({ kind: 'info', message }),
  success: (message: string) => useToastStore.getState().push({ kind: 'success', message }),
  error: (message: string) => useToastStore.getState().push({ kind: 'error', message }, 8000),
  undo: (message: string, run: () => void) => useToastStore.getState().push({ kind: 'info', message, action: { label: 'Undo', run } }, 10000),
}
