import type { ReactNode } from 'react'

export function StatCard({ label, value, hint, bar }: { label: string; value: ReactNode; hint?: ReactNode; bar?: { pct: number; color: string } }) {
  return (
    <div className="card flex flex-col gap-1.5 p-4">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className="num text-[26px] font-semibold leading-none">{value}</div>
      {bar && (
        <div className="h-1 overflow-hidden rounded bg-line2" role="presentation">
          <i className="block h-full rounded" style={{ width: `${Math.min(100, Math.max(0, bar.pct))}%`, background: bar.color }} />
        </div>
      )}
      {hint && <div className="text-xs text-muted">{hint}</div>}
    </div>
  )
}
