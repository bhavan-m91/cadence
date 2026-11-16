import clsx from 'clsx'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '@/api/errors'
import { useIdeal, useIdealProgress, useSaveIdeal } from '@/api/hooks/useIdeal'
import { useCategories, useTags, type FlatCategory, flattenCategories } from '@/api/hooks/useTaxonomy'
import type { CategoryNode, IdealProgressRow } from '@/api/types'
import { TagChip } from '@/components/domain/Chips'
import { LensNotice, LensToggle } from '@/components/layout/LensToggle'
import { PageHeader } from '@/components/layout/PageHeader'
import { inLens, useLensStore } from '@/stores/lensStore'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { ErrorState, Skeleton } from '@/components/ui/Feedback'
import { Field, Input, Select } from '@/components/ui/Field'
import { Icon } from '@/components/ui/Icon'
import { Tooltip } from '@/components/ui/Tooltip'
import { addDays, dayAndMonth, hm, todayIn, weekStartOf } from '@/lib/time'
import { useAuthStore } from '@/stores/authStore'
import { toast } from '@/stores/toastStore'
import { usePreferences } from '@/api/hooks/useSettings'

type Dist = 'all_days' | 'weekdays' | 'weekend'
const STEP = 30
const DAY = 1440
const WEEK = 10080
const DIST_LABEL: Record<Dist, string> = { all_days: 'Every day', weekdays: 'Weekdays', weekend: 'Weekend' }
const ROOTS = ['work', 'personal', 'sleep'] as const
const ROOT_LABEL = { work: 'Work', personal: 'Personal', sleep: 'Sleep' }
const ROOT_HINT = { work: 'Focus, meetings, admin', personal: 'Health, people, rest', sleep: 'Night sleep and naps' }

interface Model { day: Record<string, number>; week: Record<string, number>; dist: Record<string, Dist> }
const sum = (r: Record<string, number>) => Object.values(r).reduce((a, b) => a + b, 0)
const eq = (a: Record<string, unknown>, b: Record<string, unknown>) => {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  return [...keys].every((k) => (a[k] ?? 0) === (b[k] ?? 0))
}

/** The categories an allocation can sit on: each root's children, the childless Sleep root, and anything already allocated (an antichain, FR-107). */
function selectableRows(tree: CategoryNode[] | undefined, allocated: Set<string>): FlatCategory[] {
  const all = flattenCategories(tree)
  const byId = new Map(all.map((c) => [c.id, c]))
  const underAllocated = (c: FlatCategory) => all.some((x) => allocated.has(x.id) && x.id !== c.id && (c.path_names.startsWith(x.path_names + ' ›') || x.path_names.startsWith(c.path_names + ' ›')))
  return all.filter((c) => {
    if (allocated.has(c.id)) return true
    if (underAllocated(c)) return false
    if (c.depth === 2) return true
    return c.depth === 1 && c.root_kind === 'sleep' && !(byId.get(c.id)?.children ?? []).length
  })
}

function Stepper({ value, onChange, label, step = STEP, max }: { value: number; onChange: (v: number) => void; label: string; step?: number; max?: number }) {
  return (
    <span className="flex items-center gap-1.5">
      <button type="button" aria-label={`Decrease ${label}`} disabled={value <= 0} onClick={() => onChange(Math.max(0, value - step))}
        className="flex size-[30px] items-center justify-center rounded-lg border border-line bg-card text-muted hover:border-ghostline hover:text-ink disabled:opacity-40"><Icon name="minus" size={13} strokeWidth={2.2} /></button>
      <b className="num w-[54px] text-center text-[13px] font-semibold" aria-live="polite">{hm(value)}</b>
      <button type="button" aria-label={`Increase ${label}`} disabled={max !== undefined && value >= max} onClick={() => onChange(value + step)}
        className="flex size-[30px] items-center justify-center rounded-lg border border-line bg-card text-muted hover:border-ghostline hover:text-ink disabled:opacity-40"><Icon name="plus" size={13} strokeWidth={2.2} /></button>
    </span>
  )
}

function Ring({ parts, total }: { parts: { color: string; minutes: number }[]; total: number }) {
  const R = 96, C = 2 * Math.PI * R
  let offset = 0
  const scale = total > DAY ? DAY / total : 1
  return (
    <svg viewBox="0 0 240 240" className="block size-full" role="img" aria-label={`${hm(total)} of 24 hours assigned`}>
      <circle cx="120" cy="120" r={R} fill="none" stroke="var(--line2)" strokeWidth="24" />
      {parts.filter((p) => p.minutes > 0).map((p, i) => {
        const len = (p.minutes / DAY) * C * scale
        const el = <circle key={i} cx="120" cy="120" r={R} fill="none" stroke={p.color} strokeWidth="24" strokeDasharray={`${Math.max(0, len - 2)} ${C}`} strokeDashoffset={-offset} transform="rotate(-90 120 120)" />
        offset += len
        return el
      })}
    </svg>
  )
}

const Alert = ({ tone, children }: { tone: 'bad' | 'good'; children: React.ReactNode }) => (
  <div role={tone === 'bad' ? 'alert' : 'status'} className={clsx('flex items-center gap-3 rounded-[13px] border px-3.5 py-3', tone === 'bad' ? 'border-bad/30 bg-bad/[.08]' : 'border-good/30 bg-good/[.08]')}>
    <span className={clsx('flex size-7 flex-none items-center justify-center rounded-lg text-white', tone === 'bad' ? 'bg-bad' : 'bg-good')}><Icon name={tone === 'bad' ? 'alert' : 'check'} size={15} strokeWidth={2} /></span>
    <p className="m-0 flex-1 text-[12.5px] leading-[1.45]">{children}</p>
  </div>
)

function GroupChip({ kind, color }: { kind: (typeof ROOTS)[number]; color: string }) {
  return (
    <span className="inline-flex items-center gap-[5px] rounded-full px-2 py-0.5 pl-[7px] text-[11px] font-semibold leading-normal" style={{ background: `color-mix(in srgb, ${color} 15%, var(--card))`, color: 'var(--ink)' }}>
      <i className="size-[7px] rounded-[2px]" style={{ background: color }} />{ROOT_LABEL[kind]}
    </span>
  )
}

export function IdealPage() {
  const user = useAuthStore((s) => s.user)!
  const tz = user.timezone
  const nav = useNavigate()
  const { data: prefs } = usePreferences()
  const { data: tree, isLoading: loadingCats } = useCategories()
  const day = useIdeal('day'), week = useIdeal('week')
  const progress = useIdealProgress('week')
  const { data: tags } = useTags()
  const save = useSaveIdeal()

  const base = useMemo<Model>(() => {
    const m: Model = { day: {}, week: {}, dist: {} }
    for (const a of day.data?.current?.allocations ?? []) m.day[a.category_id] = a.minutes
    for (const a of week.data?.current?.allocations ?? []) { m.week[a.category_id] = a.minutes; m.dist[a.category_id] = a.distribution as Dist }
    return m
  }, [day.data, week.data])
  const [m, setM] = useState<Model>(base)
  useEffect(() => setM(base), [base])

  const allocated = useMemo(() => new Set([...Object.keys(m.day), ...Object.keys(m.week)].filter((k) => (m.day[k] ?? 0) > 0 || (m.week[k] ?? 0) > 0)), [m])
  const rows = useMemo(() => selectableRows(tree, new Set([...Object.keys(base.day), ...Object.keys(base.week)])), [tree, base])
  const roots = useMemo(() => new Map((tree ?? []).map((r) => [r.root_kind, r])), [tree])
  const lens = useLensStore((s) => s.lens)
  // The lens only hides rows; totals still add up every row, since a template must cover the whole 24h and 168h.
  const grouped = ROOTS.map((k) => ({ kind: k, root: roots.get(k), rows: rows.filter((r) => r.root_kind === k) })).filter((g) => g.root && g.rows.length && inLens(lens, g.kind))

  const dayTotal = sum(m.day), weekTotal = sum(m.week)
  const dayDirty = !eq(m.day, base.day), weekDirty = !eq(m.week, base.week) || !eq(m.dist as any, base.dist as any)
  const dirty = dayDirty || weekDirty
  const dayOk = dayTotal === DAY, weekOk = weekTotal === WEEK
  const canSave = dirty && (!dayDirty || dayOk) && (!weekDirty || weekOk)
  const rootSum = (kind: string, src: Record<string, number>) => rows.filter((r) => r.root_kind === kind).reduce((a, r) => a + (src[r.id] ?? 0), 0)
  const prog = new Map<string, IdealProgressRow>((progress.data?.rows ?? []).map((r) => [r.category_id, r]))

  const setDay = (id: string, v: number) => setM((s) => ({ ...s, day: { ...s.day, [id]: v } }))
  const setWeek = (id: string, v: number) => setM((s) => ({ ...s, week: { ...s.week, [id]: v }, dist: { ...s.dist, [id]: s.dist[id] ?? 'all_days' } }))
  const [remainderTo, setRemainderTo] = useState('')
  useEffect(() => { if (!remainderTo && rows.length) setRemainderTo((rows.find((r) => r.name === 'Entertainment') ?? rows[0]).id) }, [rows, remainderTo])
  const assignRemainder = (kind: 'day' | 'week') => {
    const left = (kind === 'day' ? DAY : WEEK) - (kind === 'day' ? dayTotal : weekTotal)
    if (left <= 0 || !remainderTo) return
    if (kind === 'day') setDay(remainderTo, (m.day[remainderTo] ?? 0) + left)
    else setWeek(remainderTo, (m.week[remainderTo] ?? 0) + left)
  }

  const [presetOpen, setPresetOpen] = useState(false)
  const [rebalance, setRebalance] = useState('')
  const fillFromDay = () => setM((s) => ({ ...s, week: Object.fromEntries(Object.entries(s.day).filter(([, v]) => v > 0).map(([k, v]) => [k, v * 7])), dist: Object.fromEntries(Object.keys(s.day).map((k) => [k, 'all_days' as Dist])) }))
  const weekdaysPreset = () => {
    const week: Record<string, number> = {}, dist: Record<string, Dist> = {}
    for (const r of rows) {
      const d = m.day[r.id] ?? 0
      if (!d) continue
      const isWork = r.root_kind === 'work'
      week[r.id] = d * (isWork ? 5 : 7)
      dist[r.id] = isWork ? 'weekdays' : 'all_days'
    }
    const target = rebalance || remainderTo
    week[target] = (week[target] ?? 0) + (WEEK - sum(week))
    dist[target] ??= 'all_days'
    setM((s) => ({ ...s, week, dist }))
    setPresetOpen(false)
  }

  // ---- save with an effective date (FR-111)
  const [saveOpen, setSaveOpen] = useState(false)
  const today = todayIn(tz)
  const weekStart = weekStartOf(today, prefs?.week_start ?? 1)
  const [when, setWhen] = useState<'today' | 'week' | 'custom'>('week')
  const [custom, setCustom] = useState(today)
  const [saveError, setSaveError] = useState<string>()
  const effective = when === 'today' ? today : when === 'week' ? weekStart : custom
  const doSave = async () => {
    setSaveError(undefined)
    try {
      if (dayDirty) await save.mutateAsync({ kind: 'day', effective_from: effective, allocations: Object.entries(m.day).filter(([, v]) => v > 0).map(([category_id, minutes]) => ({ category_id, minutes })) })
      if (weekDirty) await save.mutateAsync({ kind: 'week', effective_from: effective, allocations: Object.entries(m.week).filter(([, v]) => v > 0).map(([category_id, minutes]) => ({ category_id, minutes, distribution: m.dist[category_id] ?? 'all_days' })) })
      toast.success(`Saved. Applies from ${dayAndMonth(effective)}.`)
      setSaveOpen(false)
    } catch (e) { setSaveError(errorMessage(e)) }
  }

  const loading = loadingCats || day.isLoading || week.isLoading
  const goalTags = (tags ?? []).filter((t) => t.goal_kind !== 'tracked' && t.goal_weekly_minutes)
  const remDay = DAY - dayTotal, remWeek = WEEK - weekTotal
  const dayMsg = remDay === 0 ? { t: 'Exactly 24h', c: 'var(--good)' } : remDay > 0 ? { t: `${hm(remDay)} left to assign`, c: 'var(--bad)' } : { t: `${hm(-remDay)} over`, c: 'var(--bad)' }
  const maxDay = Math.max(...Object.values(m.day), 60)

  return (
    <>
      <PageHeader title="Ideal Day & Week" subtitle="How you'd like your time to split · the daily view compares to the day, the weekly view to the week">
        <LensToggle />
        <Button icon="x" onClick={() => setM(base)} disabled={!dirty}>Reset</Button>
        <Button variant="primary" icon="check" disabled={!canSave} title={canSave ? 'Save a new version' : dirty ? 'Each template must add up exactly (24h day, 168h week)' : 'Nothing to save'} onClick={() => { setSaveError(undefined); setSaveOpen(true) }}>Save</Button>
      </PageHeader>
      <LensNotice />

      <div className="flex flex-col gap-4 p-4 md:px-7 md:py-[22px] md:pb-10">
        {loading && <Skeleton className="h-96" />}
        {(day.error || week.error) && <ErrorState error={day.error ?? week.error} onRetry={() => { day.refetch(); week.refetch() }} />}

        {!loading && (
          <>
            {!dayOk || !weekOk ? (
              <Alert tone="bad"><b className="font-semibold">{[!dayOk && `Ideal day is ${remDay > 0 ? `${hm(remDay)} short of` : `${hm(-remDay)} over`} 24h`, !weekOk && weekTotal > 0 && `Ideal week is ${remWeek > 0 ? `${hm(remWeek)} short of` : `${hm(-remWeek)} over`} 168h`].filter(Boolean).join(' · ') || 'Set an Ideal week.'}</b> Time left unassigned means the picture won't be covered, and comparisons get skewed.</Alert>
            ) : (
              <Alert tone="good"><b className="font-semibold">Ideal day covers 24h and Ideal week covers 168h.</b> Every view has a complete picture to compare against.</Alert>
            )}

            <section className="card p-[18px]" aria-labelledby="ideal-day">
              <div className="mb-3.5 flex flex-wrap items-baseline justify-between gap-2.5"><h3 id="ideal-day" className="m-0 text-sm font-semibold">Ideal day</h3><span className="text-[11.5px] font-medium text-faint">Hours per category · − / + in 30-minute steps · must add up to 24h</span></div>
              <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_260px]">
                <div>
                  {grouped.map((g) => (
                    <div key={g.kind} className="mb-3">
                      <div className="flex items-center gap-2.5 pb-2 pl-0.5 pr-0.5 pt-1.5">
                        <GroupChip kind={g.kind} color={g.root!.color} /><span className="text-[11.5px] text-faint">{ROOT_HINT[g.kind]}</span>
                        <span className="num ml-auto text-sm font-semibold">{hm(rootSum(g.kind, m.day))}</span>
                      </div>
                      {g.rows.map((r) => (
                        <div key={r.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3.5 gap-y-1.5 border-t border-line2 px-0.5 py-[7px] sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_auto]">
                          <span className="flex min-w-0 items-center gap-[9px] text-[13px] font-medium"><i className="size-2.5 flex-none rounded-[3px]" style={{ background: r.color }} /><span className="truncate">{r.name}</span>{r.counts_as_focus && <small className="text-[11px] font-medium text-faint">focus</small>}</span>
                          <span className="h-2.5 overflow-hidden rounded-[5px] bg-line2 max-sm:order-3 max-sm:col-span-2" aria-hidden><i className="block h-full rounded-[5px]" style={{ width: `${Math.min(100, ((m.day[r.id] ?? 0) / maxDay) * 100)}%`, background: r.color }} /></span>
                          <Stepper value={m.day[r.id] ?? 0} onChange={(v) => setDay(r.id, v)} label={r.name} max={DAY} />
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
                <div>
                  <div className="relative mx-auto size-[240px] max-w-full">
                    <Ring total={dayTotal} parts={ROOTS.map((k) => ({ color: roots.get(k)?.color ?? 'var(--accent)', minutes: rootSum(k, m.day) }))} />
                    <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                      <b className="num text-[30px] font-semibold leading-none">{hm(dayTotal)}</b>
                      <span className="mt-1 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-faint">of 24h</span>
                      <em className="mt-1.5 text-xs font-semibold not-italic" style={{ color: dayMsg.c }}>{dayMsg.t}</em>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-col gap-2">
                    {ROOTS.map((k) => <div key={k} className="flex items-center gap-[9px] text-[12.5px]"><i className="size-[9px] rounded-[3px]" style={{ background: roots.get(k)?.color }} />{ROOT_LABEL[k]}<b className="num ml-auto font-semibold">{hm(rootSum(k, m.day))}</b></div>)}
                  </div>
                  {remDay > 0 && (
                    <div className="mt-4 flex flex-col gap-2 rounded-xl border border-line bg-line2/50 p-3">
                      <label className="text-xs font-semibold text-muted" htmlFor="rem-day">Assign the remaining {hm(remDay)} to…</label>
                      <div className="flex gap-2"><Select id="rem-day" dense value={remainderTo} onChange={(e) => setRemainderTo(e.target.value)}>{rows.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</Select><Button size="md" onClick={() => assignRemainder('day')}>Assign</Button></div>
                    </div>
                  )}
                </div>
              </div>
            </section>

            <section className="card p-[18px]" aria-labelledby="ideal-week">
              <div className="mb-3.5 flex flex-wrap items-baseline justify-between gap-2.5"><h3 id="ideal-week" className="m-0 text-sm font-semibold">Ideal week</h3><span className="text-[11.5px] font-medium text-faint">Weekly totals, not 7 copies of a day · weekends can look completely different</span></div>

              <div className="max-md:hidden overflow-x-auto">
                <table className="w-full min-w-[900px] border-collapse">
                  <thead><tr>{['Category', 'Hours / week', '≈ per day', 'Spread', 'This week so far · line = where you should be today', 'Status'].map((h, i) => <th key={h} scope="col" className={clsx('border-b border-line px-2.5 pb-2.5 text-left text-[10.5px] font-semibold uppercase tracking-[0.04em] text-faint', (i === 1 || i === 2 || i === 5) && 'text-right')}>{h}</th>)}</tr></thead>
                  <tbody>
                    {grouped.map((g) => (
                      <WeekGroup key={g.kind} g={g} m={m} setWeek={setWeek} setDist={(id, d) => setM((s) => ({ ...s, dist: { ...s.dist, [id]: d } }))} prog={prog} total={rootSum(g.kind, m.week)} />
                    ))}
                    <tr><td className="px-2.5 pt-3 text-[12.5px] font-semibold">Total</td>
                      <td className="px-2.5 pt-3 text-right"><span className={clsx('num inline-flex items-center gap-[5px] rounded-full px-[9px] py-[3px] text-xs font-bold', weekOk ? 'bg-good/15 text-good' : 'bg-bad text-white')}>{hm(weekTotal)} / 168h</span></td>
                      <td className="px-2.5 pt-3 text-right text-[12.5px] text-muted">24h</td>
                      <td colSpan={3} className="px-2.5 pt-3 text-[12.5px] font-medium text-muted">{weekTotal === 0 ? 'No Ideal week yet. Fill it from your Ideal day below.' : weekOk ? 'Adds up to 7 days.' : remWeek > 0 ? `${hm(remWeek)} left to assign.` : `${hm(-remWeek)} over.`}</td></tr>
                  </tbody>
                </table>
              </div>

              <ul className="m-0 flex list-none flex-col gap-2.5 p-0 md:hidden">
                {rows.filter((r) => inLens(lens, r.root_kind)).map((r) => (
                  <li key={r.id} className="rounded-xl border border-line p-3">
                    <div className="flex items-center gap-2 text-[13px] font-semibold"><i className="size-2.5 rounded-[3px]" style={{ background: r.color }} />{r.name}<span className="ml-auto num text-xs font-medium text-muted">≈ {hm(Math.round((m.week[r.id] ?? 0) / ({ all_days: 7, weekdays: 5, weekend: 2 } as const)[m.dist[r.id] ?? 'all_days']))}/day</span></div>
                    <div className="mt-2 flex items-center justify-between gap-2"><Stepper value={m.week[r.id] ?? 0} onChange={(v) => setWeek(r.id, v)} label={r.name} max={WEEK} />
                      <Select dense aria-label={`${r.name} spread`} className="!w-auto" value={m.dist[r.id] ?? 'all_days'} onChange={(e) => setM((s) => ({ ...s, dist: { ...s.dist, [r.id]: e.target.value as Dist } }))}>{(Object.keys(DIST_LABEL) as Dist[]).map((d) => <option key={d} value={d}>{DIST_LABEL[d]}</option>)}</Select></div>
                    <Pace row={prog.get(r.id)} weekly={m.week[r.id] ?? 0} />
                  </li>
                ))}
                <li className="flex items-center justify-between rounded-xl bg-line2 px-3 py-2.5 text-[12.5px] font-semibold">Total<span className={clsx('num rounded-full px-[9px] py-[3px] text-xs font-bold', weekOk ? 'bg-good/15 text-good' : 'bg-bad text-white')}>{hm(weekTotal)} / 168h</span></li>
              </ul>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button type="button" onClick={fillFromDay} disabled={dayTotal === 0} className="h-8 rounded-lg border border-line bg-card px-3 text-xs font-semibold hover:border-ghostline disabled:opacity-50">Fill from Ideal day × 7</button>
                <button type="button" onClick={() => { setRebalance(remainderTo); setPresetOpen(true) }} disabled={dayTotal === 0} className="h-8 rounded-lg border border-line bg-card px-3 text-xs font-semibold hover:border-ghostline disabled:opacity-50">Weekdays + lighter weekends</button>
                {remWeek > 0 && weekTotal > 0 && <Button size="sm" onClick={() => assignRemainder('week')}>Assign remaining {hm(remWeek)} to {rows.find((r) => r.id === remainderTo)?.name ?? '…'}</Button>}
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line2 pt-3.5 text-[12.5px] text-muted">
                <span>Limits that overlap other categories (not part of the 168h):</span>
                {goalTags.length === 0 && <span>none yet. <button className="font-semibold text-accent-ink" onClick={() => nav('/tags')}>Add a weekly cap to a tag</button></span>}
                {goalTags.map((t) => (
                  <span key={t.id} className="inline-flex items-center gap-2 rounded-[10px] border border-line px-2.5 py-1.5"><TagChip name={t.name} color={t.color} over={t.goal_status === 'over'} />{t.goal_kind === 'max' ? 'max' : 'min'} <b className="num text-ink">{hm(t.goal_weekly_minutes!)}</b> / week · this week <b className="num" style={{ color: t.goal_status === 'over' ? 'color-mix(in srgb, var(--bad) 80%, var(--ink))' : undefined }}>{hm(t.minutes_in_range)}</b></span>
                ))}
              </div>
            </section>

            <div className="grid gap-4 md:grid-cols-2">
              {(['day', 'week'] as const).map((k) => {
                const d = k === 'day' ? day.data : week.data
                return (
                  <section key={k} className="card p-[18px]">
                    <h3 className="m-0 mb-1 text-sm font-semibold">{k === 'day' ? 'Ideal day' : 'Ideal week'} versions</h3>
                    <p className="m-0 mb-3 text-xs text-muted">{k === 'day' ? 'Daily views compare to the version in force on that date.' : 'A week uses the version in force on its first day.'} Older versions are kept, so last month's comparison never changes.</p>
                    {(d?.versions ?? []).length === 0 ? <p className="m-0 text-[13px] text-muted">No saved version yet.</p> : (
                      <ol className="m-0 flex list-none flex-col gap-1.5 p-0">
                        {d!.versions.map((v, i) => (
                          <li key={v.effective_from} className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-[13px]"><span>From <b className="font-semibold">{dayAndMonth(v.effective_from)} {v.effective_from.slice(0, 4)}</b>{v.effective_from <= today && i === d!.versions.findIndex((x) => x.effective_from <= today) && <span className="ml-2 rounded-full bg-good/15 px-2 py-0.5 text-[10.5px] font-semibold text-good">In force</span>}{v.effective_from > today && <span className="ml-2 rounded-full bg-line2 px-2 py-0.5 text-[10.5px] font-semibold text-muted">Upcoming</span>}</span><span className="num text-xs text-muted">{hm(v.total_minutes)}</span></li>
                        ))}
                      </ol>
                    )}
                  </section>
                )
              })}
            </div>
          </>
        )}
      </div>

      <Dialog open={saveOpen} onOpenChange={setSaveOpen} title="Save a new version" description="Older versions are kept. Comparisons for earlier dates keep using the version that was in force then."
        footer={<><Button variant="subtle" onClick={() => setSaveOpen(false)}>Cancel</Button><Button variant="primary" loading={save.isPending} onClick={doSave}>Save from {dayAndMonth(effective)}</Button></>}>
        <div className="flex flex-col gap-4">
          <p className="m-0 text-[13px] text-muted">Saving: {[dayDirty && 'Ideal day', weekDirty && 'Ideal week'].filter(Boolean).join(' and ')}.</p>
          <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
            <legend className="mb-1.5 text-xs font-semibold text-muted">Apply from</legend>
            {([['today', `Today (${dayAndMonth(today)})`], ['week', `The start of this week (${dayAndMonth(weekStart)})`], ['custom', 'A date I choose']] as const).map(([v, l]) => (
              <label key={v} className="flex items-center gap-2.5 text-sm"><input type="radio" name="when" className="size-4 accent-[var(--accent)]" checked={when === v} onChange={() => setWhen(v)} />{l}</label>
            ))}
            {when === 'custom' && <Field label="Date">{(id) => <Input id={id} dense type="date" value={custom} min={addDays(today, -365)} onChange={(e) => setCustom(e.target.value)} />}</Field>}
          </fieldset>
          {saveError && <p role="alert" className="m-0 rounded-lg bg-bad/10 px-3 py-2 text-[13px] text-bad">{saveError}</p>}
        </div>
      </Dialog>

      <Dialog open={presetOpen} onOpenChange={setPresetOpen} title="Weekdays + lighter weekends" description="Work categories are spread over weekdays; everything else over all seven days. Then the week is rebalanced to exactly 168h."
        footer={<><Button variant="subtle" onClick={() => setPresetOpen(false)}>Cancel</Button><Button variant="primary" onClick={weekdaysPreset}>Apply</Button></>}>
        <Field label="Put the freed weekend hours into" hint="Work done on weekdays only frees up time on the weekend. Choose where it goes.">{(id) => <Select id={id} dense value={rebalance} onChange={(e) => setRebalance(e.target.value)}>{rows.map((r) => <option key={r.id} value={r.id}>{r.path_names}</option>)}</Select>}</Field>
      </Dialog>
      <span className="sr-only">{allocated.size}</span>
    </>
  )
}

function Pace({ row, weekly }: { row?: IdealProgressRow; weekly: number }) {
  if (!row || weekly === 0) return <div className="mt-2 text-[11.5px] text-faint">{weekly === 0 ? 'Not allocated' : 'Save to track this week'}</div>
  const pct = Math.min(100, (row.actual / Math.max(row.target, 1)) * 100)
  const mark = Math.min(100, (row.expected_to_date / Math.max(row.target, 1)) * 100)
  return (
    <div className="mt-2 flex items-center gap-2.5">
      <div className="relative h-2.5 min-w-[120px] flex-1 rounded-[5px] bg-line2" role="img" aria-label={`${hm(row.actual)} of ${hm(row.target)}; expected ${hm(row.expected_to_date)} by now`}>
        <i className="absolute inset-y-0 left-0 rounded-[5px]" style={{ width: `${pct}%`, background: 'var(--accent)' }} /><em className="absolute -inset-y-[3px] w-0.5 rounded-[1px] bg-ink" style={{ left: `${mark}%` }} />
      </div>
      <span className="num w-[86px] text-right text-[11.5px] font-semibold">{hm(row.actual)} / {hm(row.target)}</span>
    </div>
  )
}

const STATUS = { on_target: { t: 'On track', c: 'good' }, under: { t: 'Behind', c: 'warn' }, over: { t: 'Ahead', c: 'bad' } } as const

function WeekGroup({ g, m, setWeek, setDist, prog, total }: { g: { kind: (typeof ROOTS)[number]; root?: CategoryNode; rows: FlatCategory[] }; m: Model; setWeek: (id: string, v: number) => void; setDist: (id: string, d: Dist) => void; prog: Map<string, IdealProgressRow>; total: number }) {
  return (
    <>
      <tr><td colSpan={6} className="bg-line2 px-2.5 py-2 font-semibold"><GroupChip kind={g.kind} color={g.root!.color} /> <span className="ml-2 text-xs">{hm(total)}</span></td></tr>
      {g.rows.map((r) => {
        const weekly = m.week[r.id] ?? 0, dist = m.dist[r.id] ?? 'all_days', row = prog.get(r.id)
        const perDay = Math.round(weekly / ({ all_days: 7, weekdays: 5, weekend: 2 } as const)[dist])
        const st = row && weekly > 0 ? STATUS[row.status] : null
        return (
          <tr key={r.id}>
            <td className="border-b border-line2 px-2.5 py-[9px] text-[12.5px]"><span className="flex items-center gap-[9px] font-medium"><i className="size-2.5 flex-none rounded-[3px]" style={{ background: r.color }} />{r.name}</span></td>
            <td className="border-b border-line2 px-2.5 py-[9px] text-right"><span className="flex justify-end"><Stepper value={weekly} onChange={(v) => setWeek(r.id, v)} label={`${r.name} per week`} max={WEEK} /></span></td>
            <td className="num border-b border-line2 px-2.5 py-[9px] text-right text-[12.5px] text-muted">{weekly ? hm(perDay) : '–'}</td>
            <td className="border-b border-line2 px-2.5 py-[9px]"><Select dense aria-label={`${r.name} spread`} className="!w-auto !pr-7" disabled={weekly === 0} value={dist} onChange={(e) => setDist(r.id, e.target.value as Dist)}>{(Object.keys(DIST_LABEL) as Dist[]).map((d) => <option key={d} value={d}>{DIST_LABEL[d]}</option>)}</Select></td>
            <td className="border-b border-line2 px-2.5 py-[9px]"><Pace row={row} weekly={weekly} /></td>
            <td className="border-b border-line2 px-2.5 py-[9px] text-right">{st ? <Tooltip content={row && `Expected ${hm(row.expected_to_date)} by now, you are at ${hm(row.actual)}`}><span tabIndex={0} className={clsx('whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold', st.c === 'good' && 'bg-good/15 text-good', st.c === 'warn' && 'bg-warn/15 text-warn', st.c === 'bad' && 'bg-bad/15 text-bad')}>{st.t}</span></Tooltip> : <span className="text-xs text-faint">–</span>}</td>
          </tr>
        )
      })}
    </>
  )
}
