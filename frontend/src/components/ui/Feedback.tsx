import clsx from 'clsx'
import type { ReactNode } from 'react'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useToastStore } from '@/stores/toastStore'
import { Button } from './Button'
import { Icon, type IconName } from './Icon'

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={clsx('animate-pulse rounded-lg bg-line2', className)} />
}

export function EmptyState({ icon = 'info', title, children, action }: { icon?: IconName; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-tint text-accent-ink"><Icon name={icon} size={22} /></span>
      <h3 className="text-[15px] font-semibold">{title}</h3>
      {children && <p className="max-w-sm text-[13px] leading-relaxed text-muted">{children}</p>}
      {action}
    </div>
  )
}

/** Always offers Retry and shows the request id so a problem can be traced (PRD 8.4). */
export function ErrorState({ error, onRetry, compact }: { error: unknown; onRetry?: () => void; compact?: boolean }) {
  const rid = error instanceof ApiError ? error.requestId : null
  return (
    <div role="alert" className={clsx('flex flex-col items-center gap-2 text-center', compact ? 'p-4' : 'px-6 py-12')}>
      <span className="flex size-10 items-center justify-center rounded-xl bg-[color-mix(in_srgb,var(--bad)_12%,var(--card))] text-bad"><Icon name="alert" size={18} /></span>
      <p className="text-sm font-semibold">{errorMessage(error)}</p>
      {rid && <p className="text-[11px] text-faint">Request id {rid}</p>}
      {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}
    </div>
  )
}

export function Toaster() {
  const { toasts, dismiss } = useToastStore()
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-20 z-[60] flex flex-col items-center gap-2 px-4 md:bottom-6" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id} role={t.kind === 'error' ? 'alert' : 'status'}
          className={clsx('pointer-events-auto flex max-w-md items-center gap-3 rounded-xl px-4 py-2.5 text-[13px] font-medium shadow-lg', t.kind === 'error' ? 'bg-bad text-white' : 'bg-[var(--tipbg)] text-[var(--tipink)]')}
        >
          <span>{t.message}</span>
          {t.action && <button className="font-semibold underline underline-offset-2" onClick={() => { t.action!.run(); dismiss(t.id) }}>{t.action.label}</button>}
          <button aria-label="Dismiss" className="opacity-70 hover:opacity-100" onClick={() => dismiss(t.id)}><Icon name="x" size={14} /></button>
        </div>
      ))}
    </div>
  )
}

export function OfflineBanner() {
  const online = useOnline()
  if (online) return null
  return <div role="status" className="bg-warn px-4 py-1.5 text-center text-xs font-semibold text-white">You are offline. Changes will not save until you reconnect.</div>
}

import { useEffect, useState } from 'react'
function useOnline() {
  const [online, setOnline] = useState(() => navigator.onLine)
  useEffect(() => {
    const on = () => setOnline(true), off = () => setOnline(false)
    addEventListener('online', on); addEventListener('offline', off)
    return () => { removeEventListener('online', on); removeEventListener('offline', off) }
  }, [])
  return online
}
