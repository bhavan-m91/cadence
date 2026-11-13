import clsx from 'clsx'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { errorMessage } from '@/api/errors'
import { usePatchActivity, useTimeline } from '@/api/hooks/useActivities'
import { usePreferences } from '@/api/hooks/useSettings'
import { flattenCategories, useCategories, useTags } from '@/api/hooks/useTaxonomy'
import type { Block, DayTimeline } from '@/api/types'
import { Button, IconButton } from '@/components/ui/Button'
import { ErrorState, Skeleton } from '@/components/ui/Feedback'
import { Icon } from '@/components/ui/Icon'
import { Select } from '@/components/ui/Field'
import { Tooltip } from '@/components/ui/Tooltip'
import { PageHeader, Segmented } from '@/components/layout/PageHeader'
import { ActivityDetailPanel } from '@/features/activity/ActivityDetailPanel'
import { ActivityFormDialog, type FormDefaults } from '@/features/activity/ActivityFormDialog'
import { addDays, dayOfMonth, formatClock, formatRange, hm, isoToLocal, monthYear, rangeLabel, snap, todayIn, weekdayShort, weekDates } from '@/lib/time'
import { edge, tint } from '@/lib/colors'
import { useAuthStore } from '@/stores/authStore'
import { toast } from '@/stores/toastStore'

const HOUR_PX = 44
const GRID_H = 24 * HOUR_PX
const GUTTER = 52

function useIsMobile() {
  const q = '(max-width: 767px)'
  const [m, setM] = useState(() => matchMedia(q).matches)
  useEffect(() => { const mq = matchMedia(q); const f = () => setM(mq.matches); mq.addEventListener('change', f); return () => mq.removeEventListener('change', f) }, [])
  return m
}

interface DragState {
  block: Block; dayIndex: number; mode: 'move' | 'top' | 'bottom'
  startX: number; startY: number; startMin: number; endMin: number
  cur: { startMin: number; endMin: number; dayIndex: number }; moved: boolean
}

export function CalendarPage() {
  const { activityId } = useParams()
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const user = useAuthStore((s) => s.user)!
  const tz = user.timezone
  const { data: prefs } = usePreferences()
  const fmt = prefs?.time_format ?? '12h'
  const weekStart = prefs?.week_start ?? 1
  const mobile = useIsMobile()
  const today = todayIn(tz)

  const date = sp.get('date') ?? today
  const view = mobile || sp.get('view') !== 'week' ? 'day' : 'week' // the day is the default everywhere
  const ideal = sp.get('ideal') !== '0'
  const tagFilter = sp.get('tag') ?? ''
  const categoryFilter = sp.get('category') ?? ''
  const dates = view === 'week' ? weekDates(date, weekStart) : [date]
  const params = { from: dates[0], to: dates[dates.length - 1], ideal, ...(tagFilter && { tag_ids: [tagFilter] }), ...(categoryFilter && { category_id: categoryFilter }) }
  const { data: days, error, isLoading, refetch } = useTimeline(params)
  const { data: tree } = useCategories()
  const { data: tags } = useTags()
  const patch = usePatchActivity()

  const [logOpen, setLogOpen] = useState(sp.get('log') === '1')
  const [defaults, setDefaults] = useState<FormDefaults>()
  const [pending, setPending] = useState<Record<string, { startMin: number; endMin: number; dayIndex: number }>>({})

  const setParam = useCallback((k: string, v: string | null) => {
    const n = new URLSearchParams(sp)
    if (v === null || v === '') n.delete(k); else n.set(k, v)
    setSp(n, { replace: true })
  }, [sp, setSp])

  useEffect(() => { if (sp.get('log') === '1') { const n = new URLSearchParams(sp); n.delete('log'); setSp(n, { replace: true }) } }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const openLog = (d?: FormDefaults) => { setDefaults(d); setLogOpen(true) }
  const step = view === 'week' ? 7 : 1
  const scroller = useRef<HTMLDivElement>(null)
  useEffect(() => { scroller.current?.scrollTo({ top: 6.5 * HOUR_PX }) }, [])

  // ------------------------------------------------------------------ drag / resize
  const gridRef = useRef<HTMLDivElement>(null)
  const [drag, setDrag] = useState<DragState | null>(null)
  const dragRef = useRef<DragState | null>(null)
  dragRef.current = drag

  const minOf = (iso: string, d: DayTimeline) => Math.round((Date.parse(iso) - Date.parse(d.day_start_at)) / 60000)

  useEffect(() => {
    if (!drag) return
    const ppm = GRID_H / 1440
    const move = (e: PointerEvent) => {
      const s = dragRef.current!
      const dy = snap((e.clientY - s.startY) / ppm)
      const rect = gridRef.current!.getBoundingClientRect()
      const colW = (rect.width - GUTTER) / (days?.length ?? 1)
      let dayIndex = s.dayIndex
      if (s.mode === 'move') dayIndex = Math.min((days?.length ?? 1) - 1, Math.max(0, Math.floor((e.clientX - rect.left - GUTTER) / colW)))
      const len = s.endMin - s.startMin
      let startMin = s.startMin, endMin = s.endMin
      if (s.mode === 'move') { startMin = Math.min(1440 - len, Math.max(0, s.startMin + dy)); endMin = startMin + len }
      else if (s.mode === 'top') { startMin = Math.min(s.endMin - 5, Math.max(0, s.startMin + dy)) }
      else { endMin = Math.max(s.startMin + 5, Math.min(1440, s.endMin + dy)) }
      const moved = s.moved || Math.abs(e.clientY - s.startY) > 4 || dayIndex !== s.dayIndex
      setDrag({ ...s, cur: { startMin, endMin, dayIndex }, moved })
    }
    const up = () => {
      const s = dragRef.current!
      setDrag(null)
      if (!s.moved || (s.cur.startMin === s.startMin && s.cur.endMin === s.endMin && s.cur.dayIndex === s.dayIndex)) {
        if (!s.moved) nav(`/activities/${s.block.id}${location.search}`)
        return
      }
      const d = days![s.cur.dayIndex]
      const base = Date.parse(d.day_start_at)
      const start_at = new Date(base + s.cur.startMin * 60000).toISOString(), end_at = new Date(base + s.cur.endMin * 60000).toISOString()
      setPending((p) => ({ ...p, [s.block.id]: s.cur }))
      patch.mutate({ id: s.block.id, version: s.block.version, start_at, end_at }, {
        onSuccess: () => toast.success(s.mode === 'move' ? 'Moved' : 'Resized'),
        onError: (e) => toast.error(errorMessage(e)),
        onSettled: () => setPending((p) => { const n = { ...p }; delete n[s.block.id]; return n }),
      })
    }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up, { once: true })
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
  }, [!!drag]) // eslint-disable-line react-hooks/exhaustive-deps

  const beginDrag = (e: React.PointerEvent, b: Block, dayIndex: number, d: DayTimeline, mode: DragState['mode']) => {
    if (e.button !== 0 || e.pointerType === 'touch' || b.continues_from_previous_day || b.continues_to_next_day) return
    e.preventDefault()
    const startMin = minOf(b.start_at, d), endMin = minOf(b.end_at, d)
    setDrag({ block: b, dayIndex, mode, startX: e.clientX, startY: e.clientY, startMin, endMin, cur: { startMin, endMin, dayIndex }, moved: false })
  }

  // keyboard: arrows move focus between blocks, Enter opens (native button behaviour)
  const onBlockKey = (e: React.KeyboardEvent) => {
    if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return
    const all = [...(gridRef.current?.querySelectorAll<HTMLElement>('[data-block]') ?? [])]
    const i = all.indexOf(e.currentTarget as HTMLElement)
    if (i < 0) return
    e.preventDefault()
    const cur = (e.currentTarget as HTMLElement).getBoundingClientRect()
    if (e.key === 'ArrowDown') all[i + 1]?.focus()
    else if (e.key === 'ArrowUp') all[i - 1]?.focus()
    else {
      const dir = e.key === 'ArrowRight' ? 1 : -1
      const cand = all.filter((el) => Math.sign(el.getBoundingClientRect().left - cur.left) === dir)
      cand.sort((a, b) => Math.abs(a.getBoundingClientRect().top - cur.top) - Math.abs(b.getBoundingClientRect().top - cur.top))
      cand[0]?.focus()
    }
  }

  const anyLogged = !!days?.some((d) => d.coverage.logged > 0)
  const firstIncomplete = anyLogged ? days?.find((d) => d.date < today && !d.coverage.complete && d.coverage.unlogged > 0) : undefined
  const tagOptions = tags ?? []
  const catOptions = flattenCategories(tree)

  return (
    <>
      <PageHeader title="Calendar" subtitle={view === 'week' ? `${monthYear(dates[0])} · ${rangeLabel(dates[0], dates[6])}` : `${weekdayShort(date)} ${rangeLabel(date, date)} ${monthYear(date).split(' ').pop()}`}>
        {!mobile && <Segmented label="View" value={view} onChange={(v) => setParam('view', v === 'week' ? 'week' : null)} options={[{ value: 'day', label: 'Day' }, { value: 'week', label: 'Week' }]} />}
        <div className="flex items-center gap-1.5">
          <IconButton icon="chevronLeft" label={view === 'week' ? 'Previous week' : 'Previous day'} onClick={() => setParam('date', addDays(date, -step))} />
          <Button onClick={() => setParam('date', null)} disabled={dates.includes(today)}>Today</Button>
          <IconButton icon="chevronRight" label={view === 'week' ? 'Next week' : 'Next day'} onClick={() => setParam('date', addDays(date, step))} />
        </div>
        <Button variant="primary" icon="plus" onClick={() => openLog()} className="max-md:hidden">Log time</Button>
      </PageHeader>

      <div className="flex flex-wrap items-center gap-2 border-b border-line bg-card px-4 py-2 md:px-7">
        <label className="flex items-center gap-2 text-[12.5px] font-medium text-muted"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={ideal} onChange={(e) => setParam('ideal', e.target.checked ? null : '0')} />Ideal overlay</label>
        <Select dense aria-label="Filter by tag" className="!w-auto min-w-36" value={tagFilter} onChange={(e) => setParam('tag', e.target.value)}><option value="">All tags</option>{tagOptions.map((t) => <option key={t.id} value={t.id}>#{t.name}</option>)}</Select>
        <Select dense aria-label="Filter by category" className="!w-auto min-w-40" value={categoryFilter} onChange={(e) => setParam('category', e.target.value)}><option value="">All categories</option>{catOptions.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</Select>
        {(tagFilter || categoryFilter) && <Button size="sm" variant="subtle" onClick={() => { setParam('tag', null); setParam('category', null) }}>Clear filters</Button>}
      </div>

      {firstIncomplete && (
        <div role="alert" className="mx-4 mt-3 flex flex-wrap items-center gap-3 rounded-[13px] border border-warn/30 bg-warn/[.09] px-3.5 py-3 md:mx-7">
          <span className="flex size-[30px] flex-none items-center justify-center rounded-lg bg-warn text-white"><Icon name="alert" size={16} /></span>
          <p className="m-0 min-w-0 flex-1 text-[12.5px] leading-snug"><b>{weekdayShort(firstIncomplete.date)} {dayOfMonth(firstIncomplete.date)} adds up to {hm(firstIncomplete.coverage.logged)}, not {hm(firstIncomplete.coverage.elapsed)}.</b> Click a hatched gap to fill it.</p>
          {firstIncomplete.gaps[0] && <Button size="sm" className="!border-transparent !bg-warn !text-white" onClick={() => { const g = firstIncomplete.gaps[0]; openLog({ date: firstIncomplete.date, start: isoToLocal(g.start_at, tz).time, end: isoToLocal(g.end_at, tz).time }) }}>Fill gaps</Button>}
        </div>
      )}

      {mobile && (
        <div className="flex gap-1.5 overflow-x-auto px-4 pt-3" role="tablist" aria-label="Day">
          {weekDates(date, weekStart).map((d) => (
            <button key={d} role="tab" aria-selected={d === date} onClick={() => setParam('date', d)} className={clsx('flex min-h-11 min-w-[46px] flex-col items-center justify-center rounded-xl border text-xs', d === date ? 'border-accent bg-tint font-semibold text-accent-ink' : 'border-line bg-card text-muted')}>
              <span>{weekdayShort(d)}</span><span className="num text-sm">{dayOfMonth(d)}</span>
            </button>
          ))}
        </div>
      )}

      <div className="p-4 md:px-7 md:py-4">
        {error && <ErrorState error={error} onRetry={() => refetch()} />}
        {isLoading && <Skeleton className="h-[480px]" />}
        {days && (
          <div className="card overflow-hidden">
            <div ref={scroller} className="max-h-[calc(100vh-250px)] min-h-[420px] overflow-y-auto">
              <div ref={gridRef} className="min-w-[620px] md:min-w-0" style={{ minWidth: view === 'week' && !mobile ? 760 : undefined }}>
                <div className="sticky top-0 z-20 flex border-b border-line bg-card" style={{ paddingLeft: GUTTER }}>
                  {days.map((d) => <DayHeader key={d.date} day={d} today={today} tz={tz} fmt={fmt} onUnplaced={(u) => nav(`/activities/${u}${location.search}`)} />)}
                </div>
                <div className="relative flex" style={{ height: GRID_H }}>
                  <div className="relative flex-none" style={{ width: GUTTER }} aria-hidden>
                    {Array.from({ length: 23 }, (_, i) => i + 1).map((h) => (
                      <span key={h} className="num absolute right-2 -translate-y-1/2 text-[10px] text-faint" style={{ top: h * HOUR_PX }}>{fmt === '24h' ? `${h.toString().padStart(2, '0')}:00` : h === 12 ? '12pm' : h < 12 ? `${h}am` : `${h - 12}pm`}</span>
                    ))}
                  </div>
                  {days.map((d, di) => (
                    <DayColumn key={d.date} day={d} index={di} tz={tz} fmt={fmt} today={today} drag={drag} pending={pending} showIdeal={ideal}
                      onBegin={beginDrag} onKey={onBlockKey} activeId={activityId} onOpen={(id) => nav(`/activities/${id}${location.search}`)}
                      onEmpty={(min) => openLog({ date: d.date, start: minToHhmm(snap(min, 15)), end: minToHhmm(Math.min(1440, snap(min, 15) + 60)) })}
                      onGap={(g) => openLog({ date: d.date, start: isoToLocal(g.start_at, tz).time, end: isoToLocal(g.end_at, tz).time })} />
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
        <Legend />
      </div>

      <button type="button" aria-label="Log time" onClick={() => openLog()} className="fixed bottom-[88px] right-[18px] z-20 flex size-14 items-center justify-center rounded-[17px] bg-accent text-white shadow-lg md:hidden"><Icon name="plus" size={24} strokeWidth={2.2} /></button>

      <ActivityFormDialog open={logOpen} onOpenChange={setLogOpen} defaults={defaults} />
      {activityId && <ActivityDetailPanel activityId={activityId} days={days} fmt={fmt} onClose={() => nav(`/calendar${location.search}`)} />}
    </>
  )
}

const minToHhmm = (m: number) => `${Math.floor((m % 1440) / 60).toString().padStart(2, '0')}:${(m % 60).toString().padStart(2, '0')}`

function Legend() {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[11.5px] text-muted">
      <span className="flex items-center gap-1.5"><i className="hatch-bad inline-block h-3 w-5 rounded-sm border border-dashed border-bad" />Unlogged</span>
      <span className="flex items-center gap-1.5"><i className="inline-block h-3 w-5 rounded-sm border border-dashed border-ghostline bg-card" />Planned</span>
      <span className="flex items-center gap-1.5"><i className="inline-block h-3 w-1.5 rounded-sm bg-sleep" />Ideal day (right edge)</span>
      <span>Drag a block to move it, drag its top or bottom edge to resize. Click a hatched gap to fill it.</span>
    </div>
  )
}

function DayHeader({ day, today, tz, fmt, onUnplaced }: { day: DayTimeline; today: string; tz: string; fmt: '12h' | '24h'; onUnplaced: (id: string) => void }) {
  const isToday = day.date === today
  const short = day.date < today && day.coverage.unlogged > Math.max(10, 0)
  return (
    <div className={clsx('min-w-0 flex-1 border-l border-line px-2 py-2', isToday && 'bg-tint')}>
      <div className="flex items-baseline justify-between gap-1">
        <span className={clsx('text-[11px] font-semibold uppercase tracking-wide', isToday ? 'text-accent-ink' : 'text-muted')}>{weekdayShort(day.date)}</span>
        <span className={clsx('num flex size-6 items-center justify-center rounded-full text-sm font-semibold', isToday && 'bg-accent text-white')}>{dayOfMonth(day.date)}</span>
      </div>
      <Tooltip content={day.coverage.elapsed ? <>Logged {hm(day.coverage.logged)} of {hm(day.coverage.elapsed)}{day.coverage.unlogged > 0 && <><br />{hm(day.coverage.unlogged)} not logged</>}</> : 'Nothing to log yet'}>
        <div tabIndex={0} className="mt-1 flex items-center gap-1.5 text-[11px]">
          <div className="h-1 flex-1 overflow-hidden rounded bg-line2" aria-hidden><i className={clsx('block h-full rounded', short ? 'bg-bad' : 'bg-good')} style={{ width: `${Math.round(day.coverage.pct * 100)}%` }} /></div>
          <span className={clsx('num font-semibold', short ? 'text-bad' : 'text-muted')}>{day.coverage.elapsed ? hm(day.coverage.logged) : '–'}</span>
        </div>
      </Tooltip>
      {day.unplaced.length > 0 && (
        <div className="mt-1 flex flex-col gap-0.5">
          {day.unplaced.slice(0, 2).map((u) => (
            <button key={u.id} onClick={() => onUnplaced(u.id)} title={`${u.title} · ${hm(u.minutes)} some time ${u.window_start_at ? formatClock(u.window_start_at, tz, fmt) : ''}–${u.window_end_at ? formatClock(u.window_end_at, tz, fmt) : ''}`}
              className="truncate rounded px-1.5 py-0.5 text-left text-[10.5px] font-medium" style={{ background: tint(u.category.color, 16), boxShadow: `inset 0 0 0 1px ${edge(u.category.color, 40)}` }}>
              ~ {u.title} · {hm(u.minutes)}
            </button>
          ))}
          {day.unplaced.length > 2 && <span className="px-1 text-[10.5px] text-faint">+{day.unplaced.length - 2} more</span>}
        </div>
      )}
    </div>
  )
}

interface ColProps {
  day: DayTimeline; index: number; tz: string; fmt: '12h' | '24h'; today: string; drag: DragState | null; showIdeal: boolean; activeId?: string
  pending: Record<string, { startMin: number; endMin: number; dayIndex: number }>
  onBegin: (e: React.PointerEvent, b: Block, i: number, d: DayTimeline, mode: DragState['mode']) => void
  onKey: (e: React.KeyboardEvent) => void
  onEmpty: (minute: number) => void
  onGap: (g: DayTimeline['gaps'][number]) => void
  onOpen: (id: string) => void
}

function DayColumn({ day, index, tz, fmt, today, drag, pending, showIdeal, activeId, onBegin, onKey, onEmpty, onGap, onOpen }: ColProps) {
  const total = Math.round((Date.parse(day.day_end_at) - Date.parse(day.day_start_at)) / 60000)
  const ppm = GRID_H / total
  const minOf = (iso: string) => Math.round((Date.parse(iso) - Date.parse(day.day_start_at)) / 60000)
  const nowMin = day.date === today ? Math.round((Date.now() - Date.parse(day.day_start_at)) / 60000) : null
  const idealTotal = day.ideal?.reduce((s, r) => s + r.minutes, 0) ?? 0

  const place = (b: Block) => {
    const p = pending[b.id]
    if (p && p.dayIndex === index) return { s: p.startMin, e: p.endMin }
    if (drag && drag.block.id === b.id && drag.cur.dayIndex === index) return { s: drag.cur.startMin, e: drag.cur.endMin }
    return { s: minOf(b.start_at), e: minOf(b.end_at) }
  }
  const movedAway = (b: Block) => (drag?.block.id === b.id && drag.cur.dayIndex !== index) || (pending[b.id] && pending[b.id].dayIndex !== index)
  const dragIn = drag && drag.cur.dayIndex === index && drag.block.id && !day.blocks.some((b) => b.id === drag.block.id) ? drag : null

  return (
    <div className={clsx('relative min-w-0 flex-1 border-l border-line', day.date === today && 'bg-tint/40')} data-day={day.date}
      style={{ backgroundImage: 'linear-gradient(var(--line2) 1px, transparent 1px)', backgroundSize: `100% ${HOUR_PX}px` }}
      onClick={(e) => { if (e.target === e.currentTarget && !drag) onEmpty(((e.clientY - e.currentTarget.getBoundingClientRect().top) / ppm)) }}>
      {showIdeal && day.ideal && day.ideal.length > 0 && (
        <Tooltip content={<><b>Ideal day</b>{day.ideal.map((r) => <div key={r.category_id}>{r.name} · {hm(r.minutes)}</div>)}</>} side="left">
          <div tabIndex={0} aria-label="Ideal day allocation" className="absolute inset-y-0 right-0 z-[1] flex w-[7px] flex-col opacity-70">
            {day.ideal.map((r) => <i key={r.category_id} style={{ height: `${(r.minutes / idealTotal) * 100}%`, background: r.color }} />)}
          </div>
        </Tooltip>
      )}
      {day.gaps.map((g) => {
        const s = minOf(g.start_at), e = minOf(g.end_at)
        return (
          <button key={g.start_at} type="button" aria-label={`Unlogged ${hm(g.minutes)} from ${formatClock(g.start_at, tz, fmt)} to ${formatClock(g.end_at, tz, fmt)}. Log it.`} onClick={() => onGap(g)}
            className="hatch-bad absolute left-[3px] right-2 z-[1] rounded-md border-[1.5px] border-dashed border-bad px-1.5 py-0.5 text-left text-[10.5px] font-semibold text-bad hover:brightness-95"
            style={{ top: s * ppm, height: Math.max(14, (e - s) * ppm) }}>
            {(e - s) * ppm >= 26 && <>Unlogged · {hm(g.minutes)}</>}
          </button>
        )
      })}
      {[...day.blocks, ...day.planned].map((b) => {
        if (movedAway(b)) return null
        const { s, e } = place(b)
        const planned = b.kind === 'planned'
        const dragging = drag?.block.id === b.id
        const locked = b.continues_from_previous_day || b.continues_to_next_day
        const h = Math.max(16, (e - s) * ppm)
        return (
          <Tooltip key={b.id + b.start_at} content={<><b>{b.title}</b><br />{formatRange(b.start_at, b.end_at, tz, fmt)} · {hm(b.minutes)}<br /><span className="opacity-75">{b.category.path_names}{b.tags.length > 0 && ` · ${b.tags.map((t) => '#' + t.name).join(' ')}`}</span>{b.time_certainty !== 'stated' && <><br />~ {b.time_certainty} time</>}<br /><span className="opacity-75">{locked ? 'Open for details' : 'Click to open · drag to move'}</span></>}>
            <button
              type="button" data-block={b.id} onKeyDown={onKey} onPointerDown={(ev) => onBegin(ev, b, index, day, 'move')} onClick={(ev) => { if (ev.detail === 0) onOpen(b.id) /* keyboard Enter/Space; mouse is handled by the pointer logic */ }}
              aria-label={`${b.title}, ${formatRange(b.start_at, b.end_at, tz, fmt)}, ${hm(b.minutes)}${planned ? ', planned' : ''}`}
              className={clsx('group absolute left-[3px] right-2 z-[2] overflow-hidden rounded-md px-1.5 py-[3px] text-left transition-shadow hover:z-20 hover:shadow-lg', planned && 'border-[1.5px] border-dashed bg-card', dragging && 'z-30 shadow-xl', activeId === b.id && 'ring-2 ring-accent', locked ? 'cursor-pointer' : 'cursor-grab active:cursor-grabbing', 'touch-pan-y')}
              style={{ top: s * ppm, height: h, background: planned ? undefined : tint(b.category.color, 22), borderLeft: planned ? undefined : `3px solid ${b.category.color}`, borderColor: planned ? b.category.color : undefined, opacity: dragging ? 0.9 : 1 }}>
              <span className="block truncate text-[10.5px] font-semibold leading-tight">{b.title}</span>
              {h >= 30 && <span className="num block truncate text-[9.5px] text-muted">{formatRange(b.start_at, b.end_at, tz, fmt)}</span>}
              {h >= 58 && b.tags.length > 0 && <span className="mt-0.5 block truncate text-[9.5px] text-muted">{b.tags.map((t) => '#' + t.name).join(' ')}</span>}
              {!locked && !planned && (
                <>
                  <span role="presentation" onPointerDown={(ev) => { ev.stopPropagation(); onBegin(ev, b, index, day, 'top') }} className="absolute inset-x-0 top-0 h-1.5 cursor-ns-resize" />
                  <span role="presentation" onPointerDown={(ev) => { ev.stopPropagation(); onBegin(ev, b, index, day, 'bottom') }} className="absolute inset-x-0 bottom-0 h-1.5 cursor-ns-resize" />
                </>
              )}
            </button>
          </Tooltip>
        )
      })}
      {dragIn && (() => {
        const b = dragIn.block
        return <div className="absolute left-[3px] right-2 z-30 rounded-md px-1.5 py-[3px] opacity-90 shadow-xl" style={{ top: dragIn.cur.startMin * ppm, height: Math.max(16, (dragIn.cur.endMin - dragIn.cur.startMin) * ppm), background: tint(b.category.color, 30), borderLeft: `3px solid ${b.category.color}` }}><span className="block truncate text-[10.5px] font-semibold">{b.title}</span></div>
      })()}
      {nowMin !== null && nowMin >= 0 && nowMin <= total && (
        <div className="pointer-events-none absolute inset-x-0 z-10 flex items-center" style={{ top: nowMin * ppm }} aria-hidden><i className="-ml-1 size-2 rounded-full bg-bad" /><i className="h-px flex-1 bg-bad" /></div>
      )}
    </div>
  )
}
