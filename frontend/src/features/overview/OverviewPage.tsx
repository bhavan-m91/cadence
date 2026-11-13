import clsx from 'clsx'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTimeline } from '@/api/hooks/useActivities'
import { usePreferences } from '@/api/hooks/useSettings'
import { useTasks } from '@/api/hooks/useTasks'
import type { DayTimeline } from '@/api/types'
import { CategoryChip } from '@/components/domain/Chips'
import { CoverageStrip24h } from '@/components/domain/CoverageStrip24h'
import { StatCard } from '@/components/domain/StatCard'
import { PageHeader, Segmented } from '@/components/layout/PageHeader'
import { Button, IconButton } from '@/components/ui/Button'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback'
import { Icon } from '@/components/ui/Icon'
import { Tooltip } from '@/components/ui/Tooltip'
import { addDays, dayAndMonth, dayOfMonth, formatRange, greeting, hm, rangeLabel, todayIn, weekdayLong, weekdayShort, weekDates } from '@/lib/time'
import { useAuthStore } from '@/stores/authStore'

const fillLink = (d: DayTimeline) => `/calendar?date=${d.date}&view=day`

export function OverviewPage() {
  const user = useAuthStore((s) => s.user)!
  const tz = user.timezone
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const { data: prefs } = usePreferences()
  const today = todayIn(tz)
  const scope = sp.get('scope') === 'day' ? 'day' : 'week'
  const date = sp.get('date') ?? today
  const dates = scope === 'week' ? weekDates(date, prefs?.week_start ?? 1) : [date]
  // The look-back day powers the "yesterday is short" nudge regardless of the scope shown.
  const from = scope === 'week' ? dates[0] : addDays(date, -1)
  const { data: days, error, isLoading, refetch } = useTimeline({ from, to: dates[dates.length - 1], ideal: false })
  const { data: tasks } = useTasks({ status: 'open' })
  const fmt = prefs?.time_format ?? '12h'

  const shown = (days ?? []).filter((d) => dates.includes(d.date))
  // Only nudge people who are actually logging; a brand-new account has nothing to be "short" of.
  const anyLogged = (days ?? []).some((d) => d.coverage.logged > 0)
  const short = anyLogged ? (days ?? []).filter((d) => d.date < today && !d.coverage.complete && d.coverage.unlogged > 0).slice(-1)[0] : undefined
  const loggedTotal = shown.reduce((s, d) => s + d.coverage.logged, 0)
  const unloggedTotal = shown.reduce((s, d) => s + (d.date < today ? d.coverage.unlogged : 0), 0)
  const finished = shown.filter((d) => d.date < today)
  const completeCount = finished.filter((d) => d.coverage.complete).length
  const empty = !!days && shown.every((d) => d.coverage.logged === 0)
  const deadlines = (tasks ?? []).filter((t) => t.due_date && (t.days_left ?? 99) <= 7).sort((a, b) => (a.due_date! < b.due_date! ? -1 : 1))
  const set = (k: string, v: string | null) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }) }
  const step = scope === 'week' ? 7 : 1

  return (
    <>
      <PageHeader title={`${greeting(tz)}, ${user.display_name.split(' ')[0]}`} subtitle={scope === 'week' ? `Week of ${rangeLabel(dates[0], dates[6])}` : `${weekdayLong(date)}, ${dayAndMonth(date)}`}>
        <Segmented label="Scope" value={scope} onChange={(v) => set('scope', v === 'day' ? 'day' : null)} options={[{ value: 'day', label: 'Day' }, { value: 'week', label: 'Week' }]} />
        <div className="flex items-center gap-1.5">
          <IconButton icon="chevronLeft" label="Previous" onClick={() => set('date', addDays(date, -step))} />
          <Button onClick={() => set('date', null)} disabled={dates.includes(today)}>Today</Button>
          <IconButton icon="chevronRight" label="Next" onClick={() => set('date', addDays(date, step))} />
        </div>
        <Button variant="primary" icon="plus" className="max-md:hidden" onClick={() => nav('/calendar?log=1')}>Log time</Button>
      </PageHeader>

      <div className="flex flex-col gap-4 p-4 md:px-7 md:py-5">
        {error && <ErrorState error={error} onRetry={() => refetch()} />}
        {short && (
          <div role="alert" className="flex flex-wrap items-center gap-3 rounded-[13px] border border-bad/30 bg-bad/[.08] px-3.5 py-3">
            <span className="flex size-[30px] flex-none items-center justify-center rounded-lg bg-bad text-white"><Icon name="alert" size={16} /></span>
            <p className="m-0 min-w-0 flex-1 text-[12.5px] leading-snug"><b>{short.date === addDays(today, -1) ? 'Yesterday' : `${weekdayShort(short.date)} ${dayOfMonth(short.date)}`} is {hm(short.coverage.unlogged)} short of {hm(short.coverage.elapsed)}.</b> Fill it so your week adds up.</p>
            <Button size="sm" variant="primary" onClick={() => nav(fillLink(short))}>Fill gaps</Button>
          </div>
        )}

        {isLoading && <div className="grid gap-4 md:grid-cols-4"><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div>}

        {days && empty && (
          <div className="card"><EmptyState icon="calendar" title="Nothing logged for this period yet" action={<Button variant="primary" icon="plus" onClick={() => nav('/calendar?log=1')}>Log your first activity</Button>}>
            Add what you did, or plan what is coming. Totals, gaps and your 24-hour coverage fill in as you go.
          </EmptyState></div>
        )}

        {days && !empty && (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatCard label="Logged" value={hm(loggedTotal)} hint={scope === 'week' ? 'This week so far' : 'This day'} />
              <StatCard label="Not logged" value={<span className={unloggedTotal > 0 ? 'text-bad' : undefined}>{hm(unloggedTotal)}</span>} hint="In finished days" bar={{ pct: unloggedTotal ? 100 : 0, color: 'var(--bad)' }} />
              <StatCard label="Days complete" value={<>{completeCount}<span className="text-base font-medium text-faint">/{finished.length || 0}</span></>} hint="Reached 24h of coverage" bar={{ pct: finished.length ? (completeCount / finished.length) * 100 : 0, color: 'var(--good)' }} />
              <StatCard label="Deadlines" value={deadlines.length} hint="Due within 7 days" bar={{ pct: deadlines.length ? 100 : 0, color: deadlines.some((t) => t.overdue) ? 'var(--bad)' : 'var(--warn)' }} />
            </div>

            {scope === 'week' ? <WeekColumns days={shown} today={today} onOpen={(d) => nav(`/calendar?date=${d}&view=day`)} /> : (
              <section className="card p-4 md:p-5">
                <h2 className="m-0 mb-3 text-[13.5px] font-semibold">24 hours</h2>
                {shown[0] && <CoverageStrip24h day={shown[0]} tz={tz} fmt={fmt} height={30} onGap={() => nav(`/calendar?date=${shown[0].date}&view=day`)} />}
                <ol className="m-0 mt-4 flex list-none flex-col p-0">
                  {[...(shown[0]?.blocks ?? []), ...(shown[0]?.planned ?? [])].sort((a, b) => Date.parse(a.start_at) - Date.parse(b.start_at)).map((b) => (
                    <li key={b.id + b.start_at}><button type="button" onClick={() => nav(`/activities/${b.id}`)} className="flex w-full items-center gap-3 border-b border-line2 py-2 text-left last:border-0 hover:bg-line2/60">
                      <span className="num w-[108px] flex-none text-[11.5px] text-muted">{formatRange(b.start_at, b.end_at, tz, fmt)}</span>
                      <i className="h-7 w-[3px] flex-none rounded" style={{ background: b.category.color }} />
                      <span className={clsx('min-w-0 flex-1', b.kind === 'planned' && 'opacity-60')}><span className="block truncate text-[13px] font-semibold">{b.title}</span><span className="block truncate text-[11px] text-faint">{b.kind === 'planned' ? 'Planned · ' : ''}{b.category.name}</span></span>
                      <span className="num text-xs font-semibold text-muted">{hm(b.minutes)}</span>
                    </button></li>
                  ))}
                </ol>
              </section>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              <section className="card p-4 md:p-5">
                <h2 className="m-0 mb-3 text-[13.5px] font-semibold">Deadlines</h2>
                {deadlines.length === 0 ? <p className="m-0 text-[13px] text-muted">Nothing due in the next 7 days.</p> : (
                  <ul className="m-0 flex list-none flex-col gap-2 p-0">{deadlines.slice(0, 5).map((t) => (
                    <li key={t.id}><button type="button" onClick={() => nav(`/tasks/${t.id}`)} className="flex w-full items-center gap-3 rounded-lg p-1.5 text-left hover:bg-line2">
                      <span className="flex size-11 flex-none flex-col items-center justify-center rounded-[10px] border border-line"><span className="text-[9px] font-bold uppercase text-bad">{dayAndMonth(t.due_date!).split(' ')[1]}</span><span className="num text-lg font-semibold leading-none">{dayOfMonth(t.due_date!)}</span></span>
                      <span className="min-w-0 flex-1"><span className="block truncate text-[13px] font-semibold">{t.title}</span><span className="block text-[11px] text-faint">{hm(t.logged_minutes)} logged</span></span>
                      <span className={clsx('rounded-full px-2.5 py-0.5 text-[10.5px] font-semibold', t.overdue ? 'bg-bad/15 text-bad' : 'bg-warn/15 text-warn')}>{t.overdue ? `${Math.abs(t.days_left!)}d overdue` : t.days_left === 0 ? 'Today' : t.days_left === 1 ? 'Tomorrow' : `${t.days_left} days`}</span>
                    </button></li>
                  ))}</ul>
                )}
              </section>
              <section className="card flex items-start gap-3 p-4 md:p-5">
                <span className="flex size-9 flex-none items-center justify-center rounded-xl bg-tint text-accent-ink"><Icon name="ideal" size={18} /></span>
                <div><h2 className="m-0 text-[13.5px] font-semibold">Actual vs ideal is on its way</h2><p className="m-0 mt-1 text-[13px] leading-relaxed text-muted">Adherence, focus hours, sleep drift and the category breakdown land with the analytics phase. The numbers above come straight from your logged time.</p></div>
              </section>
            </div>
          </>
        )}
      </div>
    </>
  )
}

function WeekColumns({ days, today, onOpen }: { days: DayTimeline[]; today: string; onOpen: (date: string) => void }) {
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
