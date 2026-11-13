import clsx from 'clsx'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useBreakdown, useTrends } from '@/api/hooks/useAnalytics'
import type { Banner, DayTimeline, Overview, TrendMetric } from '@/api/types'
import { ChartTable, Columns, DayClock, Heatmap, Legend, LineChart, MeterList, SegmentedBar, Treemap, type ClockArc, type HeatCell } from '@/components/charts/charts'
import { Segmented } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { ErrorState, Skeleton } from '@/components/ui/Feedback'
import { Icon } from '@/components/ui/Icon'
import { dayAndMonth, dayOfMonth, formatClock, formatRange, hm, weekdayShort, type TimeFormat } from '@/lib/time'

export const pct = (n: number | null | undefined) => (n == null ? '–' : `${Math.round(n * 100)}%`)
const sign = (n: number) => (n > 0 ? '+' : n < 0 ? '−' : '±')

export function Card({ title, sub, action, children, className }: { title: string; sub?: string; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={clsx('card min-w-0 p-4 md:p-5', className)}>
      <div className="mb-3.5 flex flex-wrap items-start justify-between gap-2"><div><h2 className="m-0 text-[13.5px] font-semibold">{title}</h2>{sub && <p className="m-0 mt-0.5 text-xs text-muted">{sub}</p>}</div>{action}</div>
      {children}
    </section>
  )
}

export function Banners({ banners }: { banners: Banner[] }) {
  const nav = useNavigate()
  return (
    <>
      {banners.map((b) => (
        <div key={b.id} role="alert" className={clsx('flex flex-wrap items-center gap-3 rounded-[13px] border px-3.5 py-3', b.severity === 'bad' ? 'border-bad/30 bg-bad/[.08]' : 'border-warn/40 bg-warn/[.08]')}>
          <span className={clsx('flex size-[30px] flex-none items-center justify-center rounded-lg text-white', b.severity === 'bad' ? 'bg-bad' : 'bg-warn')}><Icon name="alert" size={16} /></span>
          <p className="m-0 min-w-0 flex-1 text-[12.5px] font-medium leading-snug">{b.text}</p>
          <Button size="sm" variant={b.severity === 'bad' ? 'primary' : 'ghost'} onClick={() => nav(b.action.route)}>{b.action.label}</Button>
        </div>
      ))}
    </>
  )
}

function Kpi({ label, value, hint, delta, meter }: { label: string; value: React.ReactNode; hint?: React.ReactNode; delta?: React.ReactNode; meter?: { pct: number; color: string } }) {
  return (
    <div className="card flex min-w-0 flex-col gap-1.5 p-4">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className="num text-[26px] font-semibold leading-none">{value}</div>
      {meter && <div className="h-1 overflow-hidden rounded bg-line2"><i className="block h-full rounded" style={{ width: `${Math.min(100, Math.max(0, meter.pct))}%`, background: meter.color }} /></div>}
      <div className="text-xs text-muted">{hint}</div>
      {delta && <div className="text-[11.5px] font-medium text-faint">{delta}</div>}
    </div>
  )
}

export function KpiRow({ o, scope }: { o: Overview; scope: 'day' | 'week' }) {
  const k = o.kpis, prevWord = scope === 'week' ? 'last week' : 'yesterday'
  const nav = useNavigate()
  const cov = k.vs_prev.coverage_pct, foc = k.vs_prev.focus, slp = k.vs_prev.sleep_avg, adh = k.vs_prev.adherence
  const target = k.focus.target
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Kpi label="Coverage" value={pct(k.coverage_pct)} hint={k.unlogged_minutes > 0 ? `${hm(k.unlogged_minutes)} not logged` : 'Everything so far is logged'}
        meter={{ pct: k.coverage_pct * 100, color: k.coverage_pct >= 0.95 ? 'var(--good)' : 'var(--warn)' }} delta={cov != null && `${sign(cov)}${Math.abs(Math.round(cov * 100))} pts vs ${prevWord}`} />
      <Kpi label={k.adherence.provisional ? 'Adherence · so far' : 'Adherence'} value={pct(k.adherence.value)}
        hint={k.adherence.value == null ? (o.ideal_setup_needed ? <button className="font-semibold text-accent-ink hover:underline" onClick={() => nav('/ideal')}>Set up your Ideal</button> : scope === 'week' ? 'Needs one finished day' : 'No allocation to compare') : k.adherence.provisional ? 'Targets prorated to the time so far' : 'Of your Ideal, excluding sleep'}
        meter={k.adherence.value != null ? { pct: k.adherence.value * 100, color: 'var(--accent)' } : undefined} delta={adh != null && `${sign(adh)}${Math.abs(Math.round(adh * 100))} pts vs ${prevWord}`} />
      <Kpi label="Focus" value={hm(k.focus.minutes ?? 0)} hint={target ? `of ${hm(target)} ${scope === 'week' ? 'weekly ' : ''}target` : 'No focus target yet'}
        meter={target ? { pct: ((k.focus.minutes ?? 0) / target) * 100, color: 'var(--accent)' } : undefined} delta={foc != null && `${sign(foc)}${hm(Math.abs(foc))} vs ${prevWord}`} />
      <Kpi label="Sleep" value={k.sleep.avg_minutes != null ? hm(k.sleep.avg_minutes) : '–'} hint={k.sleep.avg_minutes == null ? 'No nights logged' : `${k.sleep.target ? `Target ${hm(k.sleep.target)} · ` : ''}${k.sleep.drift_minutes != null ? `bedtime drift ±${k.sleep.drift_minutes}m` : 'avg per night'}`}
        delta={slp != null && `${sign(slp)}${hm(Math.abs(slp))} vs ${prevWord}`} />
    </div>
  )
}

export function IdealCard({ o, scope, onOpen }: { o: Overview; scope: 'day' | 'week'; onOpen: (categoryId: string) => void }) {
  const nav = useNavigate()
  const c = o.charts.actual_vs_ideal
  return (
    <Card title="Actual vs your Ideal" sub={scope === 'week' ? 'Finished days only. The tick is where you should be by now.' : o.kpis.adherence.provisional ? 'Today so far. Ideal is prorated to the time that has passed.' : 'The tick is your Ideal for the day.'} className="lg:col-span-2">
      {!c ? (
        <div className="flex flex-col items-start gap-3 py-2 text-[13px] text-muted"><p className="m-0">There is no Ideal {scope} in force for this period, so there is nothing to compare against.</p><Button onClick={() => nav('/ideal')}>Set up your Ideal</Button></div>
      ) : (
        <>
          <MeterList onOpen={onOpen} items={[
            ...c.rows.map((r) => ({ key: r.category_id, label: r.name, color: r.color, actual: r.actual, target: r.target, expected: r.expected, status: r.status })),
            ...(c.unallocated_actual > 0 ? [{ key: 'other', label: 'Not in your Ideal', color: 'var(--faint)', actual: c.unallocated_actual, target: 0 }] : []),
          ]} />
          <ChartTable caption="Actual versus Ideal by category" head={['Category', 'Actual', 'Expected', 'Target', 'Difference']}
            rows={[...c.rows.map((r) => [r.name, hm(r.actual), hm(r.expected), hm(r.target), `${r.delta >= 0 ? '+' : '−'}${hm(Math.abs(r.delta))}`]), ...(c.unallocated_actual ? [['Not in your Ideal', hm(c.unallocated_actual), '–', '–', '–']] : [])]} />
        </>
      )}
    </Card>
  )
}

export function WorkPersonalCard({ o }: { o: Overview }) {
  const w = o.charts.work_vs_personal, cert = o.charts.certainty
  return (
    <Card title="Work vs personal" sub="Waking time only; sleep is not counted.">
      <SegmentedBar parts={[{ key: 'work', label: 'Work', value: w.work, color: 'var(--sky)' }, { key: 'personal', label: 'Personal', value: w.personal, color: 'var(--teal)' }]} />
      <dl className="m-0 mt-4 grid gap-2 border-t border-line2 pt-3 text-[12.5px]">
        <div className="flex justify-between gap-3"><dt className="text-muted">Work outside the office</dt><dd className="num m-0 font-semibold">{hm(w.work_outside_office)}</dd></div>
        <div className="flex justify-between gap-3"><dt className="text-muted">Personal during office hours</dt><dd className="num m-0 font-semibold">{hm(w.personal_in_office_hours)}</dd></div>
        <div className="flex justify-between gap-3"><dt className="text-muted">Stated times</dt><dd className="num m-0 font-semibold">{hm(cert.recorded)}</dd></div>
        <div className="flex justify-between gap-3"><dt className="text-muted">Estimated times</dt><dd className="num m-0 font-semibold">{hm(cert.estimated)}</dd></div>
      </dl>
    </Card>
  )
}

export function SleepCard({ o, dates, tz, fmt }: { o: Overview; dates: string[]; tz: string; fmt: TimeFormat }) {
  const s = o.charts.sleep, byDate = new Map(s.nights.map((n) => [n.date, n]))
  const items = dates.map((d) => { const n = byDate.get(d); return { key: d, label: weekdayShort(d), sub: String(dayOfMonth(d)), value: n?.minutes ?? 0, color: n?.short ? 'var(--warn)' : 'var(--sleep)', flag: !!n?.short, muted: !n } })
  return (
    <Card title="Sleep" sub="Counted on the day you wake up. Amber bars are short nights.">
      <Columns items={items} target={s.target} targetLabel={s.target ? `Target ${hm(s.target)}` : undefined} height={150} />
      <dl className="m-0 mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[12.5px] text-muted">
        <div>Average <b className="num text-ink">{s.avg_minutes != null ? hm(s.avg_minutes) : '–'}</b></div>
        <div>Shortest <b className="num text-ink">{s.shortest != null ? hm(s.shortest) : '–'}</b></div>
        <div>Longest <b className="num text-ink">{s.longest != null ? hm(s.longest) : '–'}</b></div>
        <div>Short nights <b className="num text-ink">{s.short_nights}</b></div>
        {s.drift_minutes != null && <div>Bedtime drift <b className="num text-ink">±{s.drift_minutes}m</b></div>}
      </dl>
      <ChartTable caption="Sleep by night" head={['Night', 'Slept', 'Bed', 'Woke']} rows={s.nights.map((n) => [dayAndMonth(n.date), hm(n.minutes), n.bed_at ? formatClock(n.bed_at, tz, fmt) : '–', n.wake_at ? formatClock(n.wake_at, tz, fmt) : '–'])} />
    </Card>
  )
}

export function FocusCard({ o, dates }: { o: Overview; dates: string[] }) {
  const f = o.charts.focus, byDate = new Map(f.days.map((d) => [d.date, d.minutes]))
  const items = dates.map((d) => ({ key: d, label: weekdayShort(d), sub: String(dayOfMonth(d)), value: byDate.get(d) ?? 0, color: 'var(--accent)' }))
  return (
    <Card title="Focus" sub={f.target ? `${hm(f.minutes)} so far of a ${hm(f.target)} target` : 'Time in categories that count as focus'}>
      <Columns items={items} height={150} />
      <ChartTable caption="Focus minutes by day" head={['Day', 'Focus']} rows={items.map((i) => [`${i.label} ${i.sub}`, hm(i.value)])} />
    </Card>
  )
}

const TREND: Record<TrendMetric, { label: string; pct: boolean }> = { adherence: { label: 'Adherence', pct: true }, coverage: { label: 'Coverage', pct: true }, focus: { label: 'Focus', pct: false }, sleep: { label: 'Sleep', pct: false } }

export function TrendCard() {
  const [metric, setMetric] = useState<TrendMetric>('adherence')
  const q = useTrends(metric, 'week', 8)
  const cfg = TREND[metric], fmt = cfg.pct ? (n: number) => `${Math.round(n * 100)}%` : hm
  const pts = (q.data?.points ?? []).map((p) => ({ x: dayAndMonth(p.period_start), label: `Week of ${dayAndMonth(p.period_start)}`, value: p.value, target: p.target }))
  return (
    <Card title="8-week trend" sub="One point per week. The current week counts only what has finished." action={
      <Segmented label="Trend metric" value={metric} onChange={setMetric} options={(Object.keys(TREND) as TrendMetric[]).map((m) => ({ value: m, label: TREND[m].label }))} />}>
      {q.error ? <ErrorState compact error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton className="h-52" /> : (
        <div className={clsx('transition-opacity', q.isPlaceholderData && 'opacity-60')}>
          <LineChart name={`${cfg.label} by week`} points={pts} format={fmt} yMax={cfg.pct ? 1 : undefined} yTicks={cfg.pct ? [0, 0.5, 1] : undefined} />
          <ChartTable caption={`${cfg.label} by week`} head={['Week', cfg.label, 'Target']} rows={pts.map((p) => [p.x, p.value == null ? '–' : fmt(p.value), p.target == null ? '–' : fmt(p.target)])} />
        </div>
      )}
    </Card>
  )
}

export function HeatmapCard({ weekStart }: { weekStart: number }) {
  const q = useTrends('focus', 'day', 182)
  const { cells, weeks, max } = useMemo(() => {
    const pts = q.data?.points ?? []
    if (!pts.length) return { cells: [] as (HeatCell | null)[], weeks: 26, max: 1 }
    const iso = (d: string) => { const [y, m, dd] = d.split('-').map(Number); return ((new Date(Date.UTC(y, m - 1, dd)).getUTCDay() + 6) % 7) + 1 }
    const lead = (iso(pts[0].period_start) - weekStart + 7) % 7
    const list: (HeatCell | null)[] = [...Array<null>(lead).fill(null), ...pts.map((p) => ({ date: p.period_start, value: p.value ?? 0, label: hm(p.value ?? 0) }))]
    const w = Math.ceil(list.length / 7)
    while (list.length < w * 7) list.push(null)
    return { cells: list, weeks: w, max: Math.max(60, ...pts.map((p) => p.value ?? 0)) }
  }, [q.data, weekStart])
  const weekly = useMemo(() => {
    const out: [string, number][] = []
    for (let i = 0; i < cells.length; i += 7) { const row = cells.slice(i, i + 7).filter(Boolean) as HeatCell[]; if (row.length) out.push([row[0].date, row.reduce((a, c) => a + c.value, 0)]) }
    return out
  }, [cells])
  return (
    <Card title="Focus, last 26 weeks" sub="Each square is a day. Darker means more focus time.">
      {q.error ? <ErrorState compact error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton className="h-28" /> : (
        <><Heatmap cells={cells} weeks={weeks} max={max} name="Focus minutes per day over 26 weeks" /><ChartTable caption="Focus minutes per week" head={['Week of', 'Focus']} rows={weekly.map(([d, v]) => [dayAndMonth(d), hm(v)])} /></>
      )}
    </Card>
  )
}

export function TreemapCard({ from, to }: { from: string; to: string }) {
  const nav = useNavigate()
  const q = useBreakdown(from, to, 'category')
  const tiles = (q.data?.items ?? []).filter((i) => i.minutes > 0 && i.root_kind !== 'sleep').map((i) => ({ key: i.id, label: i.name, value: i.minutes, color: i.color, share: q.data!.waking_minutes ? i.minutes / q.data!.waking_minutes : 0 }))
  return (
    <Card title="Where the time went" sub="Area is time. Click a tile to see those activities on the Calendar.">
      {q.error ? <ErrorState compact error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton className="h-56" /> : tiles.length === 0 ? <p className="m-0 text-[13px] text-muted">Nothing logged in this period.</p> : (
        <div className={clsx('transition-opacity', q.isPlaceholderData && 'opacity-60')}>
          <Treemap tiles={tiles} onOpen={(t) => nav(`/calendar?date=${from}&category=${t.key}`)} />
          <ChartTable caption="Time by category" head={['Category', 'Time', 'Share of waking time']} rows={tiles.sort((a, b) => b.value - a.value).map((t) => [t.label, hm(t.value), pct(t.share)])} />
        </div>
      )}
    </Card>
  )
}

export function TopTasksCard({ o }: { o: Overview }) {
  const nav = useNavigate()
  const tasks = o.charts.top_tasks, max = Math.max(1, ...tasks.map((t) => t.minutes))
  return (
    <Card title="Top tasks">
      {tasks.length === 0 ? <p className="m-0 text-[13px] text-muted">No time is linked to tasks yet.</p> : (
        <ul className="m-0 flex list-none flex-col gap-2.5 p-0">{tasks.map((t) => (
          <li key={t.task_id}><button type="button" onClick={() => nav(`/tasks/${t.task_id}`)} className="grid w-full grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 rounded-lg p-1 text-left hover:bg-line2/60">
            <span className="truncate text-[12.5px] font-semibold">{t.title}</span><span className="num text-xs font-semibold text-muted">{hm(t.minutes)}</span>
            <span className="col-span-2 h-2 rounded bg-line2"><i className="block h-full rounded-[4px] bg-accent" style={{ width: `${(t.minutes / max) * 100}%` }} /></span>
          </button></li>
        ))}</ul>
      )}
    </Card>
  )
}

export function TagGoalsCard({ o }: { o: Overview }) {
  const goals = o.charts.tag_goals
  if (goals.length === 0) return null
  return (
    <Card title="Tag limits this week">
      <ul className="m-0 flex list-none flex-col gap-2.5 p-0">{goals.map((t) => {
        const cap = t.goal_weekly_minutes ?? 0, over = t.goal_status === 'over'
        return (
          <li key={t.tag_id} className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-2 text-[12.5px]"><span className="flex items-center gap-2 font-semibold"><i className="size-2.5 rounded-[3px]" style={{ background: t.color }} />#{t.name}</span>
              <span className="num text-xs"><b className={over ? 'text-bad' : ''}>{hm(t.minutes)}</b> <span className="text-faint">{t.goal_kind === 'max' ? 'max' : 'min'} {hm(cap)}</span>{over && <span className="ml-1.5 rounded-full bg-bad/15 px-1.5 py-0.5 text-[10.5px] font-semibold text-bad">Over</span>}</span></div>
            <span className="relative h-2 rounded bg-line2"><i className="absolute inset-y-0 left-0 rounded-[4px]" style={{ width: `${Math.min(100, (t.minutes / Math.max(cap, t.minutes, 1)) * 100)}%`, background: over ? 'var(--bad)' : t.color }} /><em className="absolute -inset-y-[2px] w-0.5 bg-ink" style={{ left: `${(cap / Math.max(cap, t.minutes, 1)) * 100}%` }} /></span>
          </li>
        )
      })}</ul>
    </Card>
  )
}

export function DeadlinesCard({ o }: { o: Overview }) {
  const nav = useNavigate()
  return (
    <Card title="Deadlines" sub="Open tasks due within 7 days, and anything overdue.">
      {o.deadlines.length === 0 ? <p className="m-0 text-[13px] text-muted">Nothing due in the next 7 days.</p> : (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">{o.deadlines.slice(0, 5).map((t) => (
          <li key={t.task_id}><button type="button" onClick={() => nav(`/tasks/${t.task_id}`)} className="flex w-full items-center gap-3 rounded-lg p-1.5 text-left hover:bg-line2">
            <span className="flex size-11 flex-none flex-col items-center justify-center rounded-[10px] border border-line"><span className="text-[9px] font-bold uppercase text-bad">{dayAndMonth(t.due_date).split(' ')[1]}</span><span className="num text-lg font-semibold leading-none">{dayOfMonth(t.due_date)}</span></span>
            <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{t.title}</span>
            <span className={clsx('rounded-full px-2.5 py-0.5 text-[10.5px] font-semibold', t.overdue ? 'bg-bad/15 text-bad' : 'bg-warn/15 text-warn')}>{t.overdue ? `${Math.abs(t.days_left)}d overdue` : t.days_left === 0 ? 'Today' : t.days_left === 1 ? 'Tomorrow' : `${t.days_left} days`}</span>
          </button></li>
        ))}</ul>
      )}
      <p className="m-0 mt-3 flex gap-4 border-t border-line2 pt-3 text-xs text-muted"><span>Journal streak <b className="num text-ink">{o.streaks.journal}</b> days</span><span>Focus streak <b className="num text-ink">{o.streaks.focus}</b> days</span></p>
    </Card>
  )
}

/** Day scope: the ring, then the hour-by-hour log with a Fill button on every gap. */
export function DayRhythm({ day, tz, fmt }: { day: DayTimeline; tz: string; fmt: TimeFormat }) {
  const nav = useNavigate()
  const start = Date.parse(day.day_start_at), mins = (iso: string) => Math.round((Date.parse(iso) - start) / 60000)
  const arcs: ClockArc[] = day.blocks.map((b) => ({ key: b.id + b.start_at, label: `${b.title} · ${hm(b.minutes)}`, startMin: mins(b.start_at), endMin: mins(b.end_at), color: b.category.color }))
  const gaps = day.gaps.map((g) => ({ startMin: mins(g.start_at), endMin: mins(g.end_at) }))
  const rows = [...day.blocks.map((b) => ({ t: Date.parse(b.start_at), kind: 'block' as const, b })), ...day.gaps.map((g) => ({ t: Date.parse(g.start_at), kind: 'gap' as const, g })), ...day.planned.map((b) => ({ t: Date.parse(b.start_at), kind: 'plan' as const, b }))].sort((a, b) => a.t - b.t)
  const legend = Array.from(new Map(day.blocks.map((b) => [b.category.id, b.category])).values()).slice(0, 8).map((c) => ({ label: c.name, color: c.color }))
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
      <Card title="24 hours" sub="Midnight is at the top. Hatched is time nobody logged.">
        <DayClock arcs={arcs} gaps={gaps} centre={hm(day.coverage.logged)} sub={`of ${hm(day.coverage.elapsed || 1440)}`} />
        <div className="mt-3"><Legend items={[...legend, ...(day.gaps.length ? [{ label: 'Unlogged', color: 'var(--bad)', hatch: true }] : [])]} /></div>
      </Card>
      <Card title="Hour by hour">
        <ol className="m-0 flex list-none flex-col p-0">
          {rows.length === 0 && <li className="py-2 text-[13px] text-muted">Nothing logged yet today.</li>}
          {rows.map((r) => r.kind === 'gap' ? (
            <li key={`g${r.t}`} className="flex items-center gap-3 border-b border-line2 py-2 last:border-0">
              <span className="num w-[108px] flex-none text-[11.5px] text-muted">{formatRange(r.g.start_at, r.g.end_at, tz, fmt)}</span><i className="hatch-bad h-7 w-[3px] flex-none rounded" />
              <span className="min-w-0 flex-1 text-[12.5px] font-semibold text-bad">Not logged · {hm(r.g.minutes)}</span>
              <Button size="sm" onClick={() => nav(`/calendar?date=${day.date}&view=day&log=1`)}>Fill</Button>
            </li>
          ) : (
            <li key={r.b.id + r.b.start_at} className="border-b border-line2 last:border-0"><button type="button" onClick={() => nav(`/activities/${r.b.id}`)} className="flex w-full items-center gap-3 py-2 text-left hover:bg-line2/60">
              <span className="num w-[108px] flex-none text-[11.5px] text-muted">{formatRange(r.b.start_at, r.b.end_at, tz, fmt)}</span><i className="h-7 w-[3px] flex-none rounded" style={{ background: r.b.category.color }} />
              <span className={clsx('min-w-0 flex-1', r.kind === 'plan' && 'opacity-60')}><span className="block truncate text-[13px] font-semibold">{r.b.title}</span><span className="block truncate text-[11px] text-faint">{r.kind === 'plan' ? 'Planned · ' : ''}{r.b.category.name}</span></span>
              <span className="num text-xs font-semibold text-muted">{hm(r.b.minutes)}</span>
            </button></li>
          ))}
        </ol>
      </Card>
    </div>
  )
}

