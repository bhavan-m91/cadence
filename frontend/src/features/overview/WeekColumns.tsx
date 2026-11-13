import clsx from 'clsx'
import type { DayTimeline } from '@/api/types'
import { CategoryChip } from '@/components/domain/Chips'
import { Tooltip } from '@/components/ui/Tooltip'
import { dayOfMonth, hm, weekdayShort } from '@/lib/time'

export function WeekColumns({ days, today, onOpen }: { days: DayTimeline[]; today: string; onOpen: (date: string) => void }) {
  return (
    <section className="card p-4 md:p-5">
      <h2 className="m-0 mb-1 text-[13.5px] font-semibold">24h coverage by day</h2>
      <p className="m-0 mb-4 text-xs text-muted">Each column is one day by category. Hatched red is time nobody logged.</p>
      <div className="flex items-end gap-2 md:gap-3">
        {days.map((d) => {
          const total = Date.parse(d.day_end_at) - Date.parse(d.day_start_at)
          const future = d.date > today
          const label = `${weekdayShort(d.date)} ${dayOfMonth(d.date)}: ${hm(d.coverage.logged)} logged${d.date < today && d.coverage.unlogged > 0 ? `, ${hm(d.coverage.unlogged)} not logged` : ''}`
          return (
            <Tooltip key={d.date} content={label}>
              <button type="button" onClick={() => onOpen(d.date)} aria-label={label} className="group flex flex-1 flex-col items-center gap-1.5">
                <div className={clsx('relative flex h-40 w-full max-w-[44px] flex-col-reverse overflow-hidden rounded-lg bg-line2 group-hover:ring-2 group-hover:ring-accent/40', future && 'border border-dashed border-ghostline opacity-50')}>
                  {[...d.blocks].sort((a, b) => Date.parse(b.start_at) - Date.parse(a.start_at)).map((b) => <i key={b.id + b.start_at} className="block w-full" style={{ height: `${((Date.parse(b.end_at) - Date.parse(b.start_at)) / total) * 100}%`, background: b.category.color }} />)}
                </div>
                <span className={clsx('text-[11px] font-semibold', d.date === today ? 'text-accent-ink' : d.date < today && d.coverage.unlogged > 0 ? 'text-bad' : 'text-muted')}>{weekdayShort(d.date)}</span>
                <span className="num text-[11px] text-faint">{future ? '–' : hm(d.coverage.logged)}</span>
              </button>
            </Tooltip>
          )
        })}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">{Array.from(new Map(days.flatMap((d) => d.blocks).map((b) => [b.category.id, b.category])).values()).slice(0, 8).map((c) => <CategoryChip key={c.id} name={c.name} color={c.color} />)}</div>
    </section>
  )
}
