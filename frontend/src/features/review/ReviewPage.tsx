import clsx from 'clsx'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useEntry, useJob, useProcessEntry } from '@/api/hooks/useJournal'
import { useAnswer, useCommit, useReview } from '@/api/hooks/useReview'
import { usePreferences } from '@/api/hooks/useSettings'
import { useCategories, useTags } from '@/api/hooks/useTaxonomy'
import type { CategoryNode, CommitBody, Review } from '@/api/types'
import { ActivityFormDialog, type FormDefaults } from '@/features/activity/ActivityFormDialog'
import { rangeToIso } from '@/components/domain/TimeRangeInput'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback'
import { Textarea } from '@/components/ui/Field'
import { Icon } from '@/components/ui/Icon'
import { dayAndMonth, formatClock, formatRange, hm, isoToLocal, weekdayShort, type TimeFormat } from '@/lib/time'
import { useAuthStore } from '@/stores/authStore'
import { toast, useToastStore } from '@/stores/toastStore'
import { DraftCard, DraftEditDialog, GapRow, initialEdit, isLater, type DraftEdit, type DraftView, type ResolutionAction } from './DraftParts'

type Edits = NonNullable<NonNullable<CommitBody['activities']>[number]['edits']>

const JOB_FAIL: Record<string, string> = {
  PROVIDER_ERROR: 'The AI service refused the request. That is a server setup problem (the model or key), not your text.',
  PROVIDER_UNAVAILABLE: 'The AI service is busy or unreachable right now.',
  INVALID_MODEL_OUTPUT: 'The AI answered in a form Cadence could not read.',
  TIMED_OUT: 'Reading took too long and was stopped.',
  INTERNAL: 'Something broke on the server while reading it.',
}

function findCategory(nodes: CategoryNode[] | undefined, id: string): CategoryNode | undefined {
  for (const n of nodes ?? []) { if (n.id === id) return n; const c = findCategory(n.children, id); if (c) return c }
}

export function ReviewPage() {
  const { entryId } = useParams()
  const [sp, setSp] = useSearchParams()
  const nav = useNavigate()
  const entry = useEntry(entryId)
  const jobId = sp.get('job') ?? entry.data?.latest_job_id ?? undefined
  const job = useJob(jobId)
  const status = job.data?.status
  const review = useReview(entryId, jobId, status === 'succeeded')
  const process = useProcessEntry()
  const goBack = () => nav('/journal')
  const rerun = async (regenerate = false, user_hint?: string) => {
    try {
      const j = await process.mutateAsync({ id: entryId!, key: crypto.randomUUID(), regenerate, user_hint })
      setSp({ job: j.job_id }, { replace: true })
    } catch (e) { toast.error(errorMessage(e)) }
  }

  if (entry.error || job.error || (review.error && !(review.error instanceof ApiError && review.error.status === 409))) {
    return <><PageHeader title="Review" back={goBack} /><ErrorState error={entry.error ?? job.error ?? review.error} onRetry={() => { entry.refetch(); job.refetch(); review.refetch() }} /></>
  }
  if (entry.data?.status === 'confirmed' && (!review.data || review.data.drafts.length === 0)) {
    return <><PageHeader title="Already saved" back={goBack} /><EmptyState icon="check" title="This entry is already saved" action={<Button variant="primary" onClick={() => nav(`/journal/${entryId}`)}>Open the entry</Button>}>Its activities are on your Calendar. Open the entry to see them or to read it again.</EmptyState></>
  }
  if (!jobId && entry.data) {
    return <><PageHeader title="Review" back={goBack} /><EmptyState icon="journal" title="Nothing to review yet" action={<Button variant="primary" loading={process.isPending} onClick={() => rerun()}>Read this entry</Button>}>This entry has not been read yet.</EmptyState></>
  }
  if (!job.data || !entry.data) return <><PageHeader title="Review" back={goBack} /><div className="p-4 md:px-7"><Skeleton className="h-64" /></div></>
  if (status === 'failed' || status === 'cancelled') {
    return (
      <><PageHeader title="Review" back={goBack} />
        <div className="mx-auto w-full max-w-lg p-4 pt-10"><div className="card flex flex-col items-center gap-3 p-8 text-center" role="alert">
          <span className="flex size-12 items-center justify-center rounded-2xl bg-bad/10 text-bad"><Icon name="alert" size={22} /></span>
          <h2 className="m-0 text-base font-semibold">Cadence could not read this entry</h2>
          <p className="m-0 text-[13px] text-muted">{(job.data.error_code && JOB_FAIL[job.data.error_code]) ?? 'Something went wrong while reading it.'} Your text is safe.</p>
          <div className="mt-2 flex flex-wrap justify-center gap-2"><Button variant="primary" icon="refresh" loading={process.isPending} onClick={() => rerun(true)}>Try again</Button><Button onClick={() => nav('/calendar?log=1')}>Enter it manually</Button></div>
        </div></div></>
    )
  }
  if (status !== 'succeeded' || !review.data) {
    return <><PageHeader title="Review" back={goBack} /><Processing started={entry.data.updated_at} /></>
  }
  return <ReviewBoard key={jobId} entryId={entryId!} jobId={jobId!} review={review.data} stale={job.data.is_stale} onRerun={rerun} rerunning={process.isPending} />
}

function Processing({ started }: { started: string }) {
  const [t, setT] = useState(0)
  useEffect(() => { const i = setInterval(() => setT((x) => x + 1), 1000); return () => clearInterval(i) }, [])
  const steps = ['Reading your words', 'Finding activities and times', 'Matching tags and tasks', 'Checking for gaps and overlaps']
  const at = Math.min(steps.length - 1, Math.floor(t / 3))
  return (
    <div className="mx-auto w-full max-w-lg p-4 pt-10" data-started={started}>
      <div className="card flex flex-col items-center gap-4 p-8 text-center" role="status" aria-live="polite">
        <span className="size-10 animate-spin rounded-full border-[3px] border-accent border-t-transparent" aria-hidden />
        <h2 className="m-0 text-base font-semibold">Reading your entry…</h2>
        <ol className="m-0 flex list-none flex-col gap-1.5 p-0 text-left text-[13px]">
          {steps.map((s, i) => <li key={s} className={clsx('flex items-center gap-2', i > at ? 'text-faint' : i === at ? 'font-semibold' : 'text-muted')}><Icon name={i < at ? 'check' : 'sparkle'} size={13} className={i < at ? 'text-good' : ''} />{s}</li>)}
        </ol>
        <p className="m-0 text-xs text-faint">{t < 20 ? 'This usually takes a few seconds.' : 'Taking longer than usual. You can leave; the result will be waiting under Journal.'}</p>
      </div>
    </div>
  )
}

function ReviewBoard({ entryId, jobId, review, stale, onRerun, rerunning }: { entryId: string; jobId: string; review: Review; stale: boolean; onRerun: (regen: boolean, hint?: string) => void; rerunning: boolean }) {
  const user = useAuthStore((s) => s.user)!
  const tz = user.timezone
  const nav = useNavigate()
  const { data: prefs } = usePreferences()
  const fmt: TimeFormat = prefs?.time_format ?? '12h'
  const { data: tree } = useCategories()
  const { data: tagList } = useTags()
  const answer = useAnswer(entryId), commit = useCommit(entryId)
  const { entry, drafts } = review

  const [include, setInclude] = useState<Record<string, boolean>>(() => Object.fromEntries(drafts.map((d) => [d.id, d.include && !isLater(d, entry.covers_end_at)])))
  const [edits, setEdits] = useState<Record<string, DraftEdit>>({})
  const [resolutions, setResolutions] = useState<Record<string, { action: ResolutionAction; existing: string }>>({})
  const [transitions, setTransitions] = useState<string[]>([])
  const [replacePrev, setReplacePrev] = useState(review.replace_candidates.length > 0)
  const [hot, setHot] = useState<string>()
  const [editing, setEditing] = useState<string>()
  const [addGap, setAddGap] = useState<FormDefaults>()
  const [regenOpen, setRegenOpen] = useState(false)
  const [hint, setHint] = useState('')
  const [discardOpen, setDiscardOpen] = useState(false)
  const [err, setErr] = useState<string>()
  const keys = useRef(new Map<string, string>())

  // New drafts after an answer re-resolve the times: keep what the person already decided, default the rest.
  useEffect(() => setInclude((p) => Object.fromEntries(drafts.map((d) => [d.id, p[d.id] ?? (d.include && !isLater(d, entry.covers_end_at))]))), [drafts, entry.covers_end_at])

  const getEdit = (d: Review['drafts'][number]) => edits[d.id] ?? initialEdit(d, tz)
  const isIn = (id: string) => include[id] !== false
  const included = drafts.filter((d) => isIn(d.id))
  const tagById = useMemo(() => new Map((tagList ?? []).map((t) => [t.id, t])), [tagList])

  const views = useMemo(() => new Map(drafts.map((d) => {
    const e = edits[d.id] ?? initialEdit(d, tz)
    const cat = findCategory(tree, e.category_id)
    const src = new Map(d.tags.filter((t) => t.tag_id).map((t) => [t.tag_id!, t]))
    const tags: DraftView['tags'] = [
      ...e.tag_ids.flatMap((id) => { const t = tagById.get(id); const s = src.get(id); return t ? [{ key: id, name: t.name, color: t.color, source: s?.source ?? 'user', isNew: false, needsCheck: !!s && s.confidence < 0.5, removable: true }] : [] }),
      ...d.tags.filter((t) => t.new && !e.removedNew.includes(t.name)).map((t) => ({ key: `new:${t.name}`, name: t.name, color: t.color, source: t.source, isNew: true, needsCheck: false, removable: true })),
    ]
    const minutes = e.range ? Math.round((Date.parse(rangeToIso(e.range, tz).end_at) - Date.parse(rangeToIso(e.range, tz).start_at)) / 60000) : e.duration
    const task = e.task_id ? d.task.task_title : e.new_task_title
    const view: DraftView = { title: e.title, description: e.description, category: { name: cat?.name ?? d.category.name, color: cat?.color ?? d.category.color }, tags, minutes: minutes ?? null, taskLabel: task ? (e.task_id ? task : `New task: ${task}`) : null }
    return [d.id, view] as const
  })), [drafts, edits, tree, tagById, tz])

  const blockersOf = (id: string) => review.blocking.filter((b) => b.draft_id === id && (b.reason !== 'OVERLAP' || !resolutions[id])).map((b) => b.reason as string)
  const blocked = included.filter((d) => blockersOf(d.id).length > 0)
  // A question about something you unticked cannot hold up saving the rest.
  const includedTemp = new Set(included.map((d) => d.temp_id))
  const openQuestions = review.questions.filter((q) => includedTemp.has(q.activity_temp_id))
  const later = drafts.filter((d) => isLater(d, entry.covers_end_at))
  // Plain words for why Save is greyed out, so nobody has to hover a disabled button to find out.
  const reasons: { text: string; to: string }[] = [
    ...(openQuestions.length ? [{ text: `Answer ${openQuestions.length === 1 ? 'the question' : `${openQuestions.length} questions`} below`, to: 'questions' }] : []),
    ...blocked.flatMap((d) => blockersOf(d.id).filter((r) => r !== 'UNANSWERED_QUESTION').map((r) => ({
      text: r === 'MISSING_DURATION' ? `Add a duration to “${views.get(d.id)?.title}”` : `Choose how to fix the overlap on “${views.get(d.id)?.title}”`, to: `draft-${d.id}` }))),
    ...(included.length === 0 ? [{ text: 'Tick at least one activity', to: '' }] : []),
  ]

  // ---- timeline summary
  const w0 = Date.parse(entry.covers_start_at), w1 = Date.parse(entry.covers_end_at), span = Math.max(1, w1 - w0)
  const pct = (iso: string) => Math.min(100, Math.max(0, ((Date.parse(iso) - w0) / span) * 100))
  const placed = included.filter((d) => d.placement === 'placed' && d.start_at && d.end_at)
  const unplacedMin = included.filter((d) => d.placement !== 'placed').reduce((a, d) => a + (views.get(d.id)?.minutes ?? 0), 0)
  const coveredMin = included.reduce((a, d) => a + (views.get(d.id)?.minutes ?? 0), 0)
  const notMentioned = Math.max(0, review.summary.not_mentioned_minutes)
  const tagCount = included.reduce((a, d) => a + (views.get(d.id)?.tags.length ?? 0), 0)

  // ---- list: drafts and gaps in time order
  const rows = useMemo(() => {
    const t = (iso: string | null) => (iso ? Date.parse(iso) : 0)
    return [
      ...drafts.map((d, i) => ({ kind: 'draft' as const, at: t(d.start_at ?? d.window_start_at), d, i })),
      ...review.gaps.map((g) => ({ kind: 'gap' as const, at: t(g.start_at), g })),
    ].sort((a, b) => a.at - b.at || (a.kind === 'draft' ? -1 : 1))
  }, [drafts, review.gaps])

  // ---- source text with highlights
  const text = entry.raw_text
  const marks = drafts.filter((d) => d.source.start != null && d.source.end != null && d.source.end > d.source.start).map((d) => ({ d, s: d.source.start!, e: d.source.end! })).sort((a, b) => a.s - b.s)
  const segs: React.ReactNode[] = []
  let cur = 0
  marks.forEach(({ d, s, e }) => {
    if (s < cur) return
    if (s > cur) segs.push(text.slice(cur, s))
    const idx = drafts.indexOf(d)
    segs.push(<mark key={d.id} id={`src-${d.id}`} onMouseEnter={() => setHot(d.id)} onMouseLeave={() => setHot(undefined)} className={clsx('rounded px-0.5 text-ink transition', hot === d.id ? 'bg-accent/35' : 'bg-accent/15', !isIn(d.id) && 'opacity-50')}>{text.slice(s, e)}<sup className="num ml-0.5 text-[9px] font-bold text-accent-ink">{idx + 1}</sup></mark>)
    cur = e
  })
  segs.push(text.slice(cur))

  // ---- commit
  const buildBody = (): CommitBody => {
    const activities = drafts.map((d) => {
      const e = getEdit(d), i = initialEdit(d, tz), ed = { clear_task: false } as Edits
      if (e.title !== i.title) ed.title = e.title
      if (e.description !== i.description) ed.description = e.description.trim() || null
      if (e.category_id !== i.category_id) ed.category_id = e.category_id
      if (JSON.stringify(e.tag_ids) !== JSON.stringify(i.tag_ids)) ed.tag_ids = e.tag_ids
      if (e.range && JSON.stringify(e.range) !== JSON.stringify(i.range)) { const r = rangeToIso(e.range, tz); ed.start_at = r.start_at; ed.end_at = r.end_at }
      if (!e.range && e.duration && e.duration !== i.duration) ed.duration_minutes = e.duration
      if (e.task_id !== i.task_id) { if (e.task_id) ed.task_id = e.task_id; else ed.clear_task = true }
      if (!e.task_id && e.new_task_title !== i.new_task_title && e.new_task_title.trim()) ed.new_task_title = e.new_task_title.trim()
      return { draft_id: d.id, include: isIn(d.id), ...(Object.keys(ed).length > 1 || ed.clear_task ? { edits: ed } : {}) }
    })
    return {
      job_id: jobId, replace_previous: replacePrev && review.replace_candidates.length > 0, activities,
      new_tags: drafts.flatMap((d) => d.tags.filter((t) => t.new).map((t) => ({ draft_id: d.id, name: t.name, keep: isIn(d.id) && !getEdit(d).removedNew.includes(t.name) }))),
      transitions: review.gaps.filter((g) => transitions.includes(g.start_at)).map((g) => ({ start_at: g.start_at, end_at: g.end_at })),
      conflict_resolutions: Object.entries(resolutions).filter(([id]) => isIn(id)).map(([draft_id, r]) => ({ draft_id, action: r.action, existing_id: r.action === 'trim_new' || r.action === 'keep_unplaced' ? null : r.existing })),
    }
  }

  const save = async () => {
    setErr(undefined)
    const body = buildBody()
    const sig = JSON.stringify(body)
    if (!keys.current.has(sig)) keys.current.set(sig, crypto.randomUUID())
    try {
      const res = await commit.mutateAsync({ ...body, key: keys.current.get(sig)! })
      const day = isoToLocal(res.activities[0]?.start_at ?? entry.covers_start_at, tz).date
      useToastStore.getState().push({ kind: 'success', message: `Saved ${res.activities.length} ${res.activities.length === 1 ? 'activity' : 'activities'}.`, action: { label: 'View on Calendar', run: () => nav(`/calendar?date=${day}`) } }, 8000)
      nav(`/journal/${entryId}`)
    } catch (e) {
      setErr(e instanceof ApiError && e.code === 'REVIEW_BLOCKED' ? 'Some activities still overlap. Choose how to resolve each overlap, then save again.' : errorMessage(e))
    }
  }

  const count = included.length
  const editingDraft = drafts.find((d) => d.id === editing) ?? null
  const gapLabel = (g: Review['gaps'][number]) => formatRange(g.start_at, g.end_at, tz, fmt)
  const sourceLabel = entry.input_method === 'dictated' ? 'dictated' : 'typed'
  const total = Math.max(1, coveredMin)
  const byCat = new Map<string, { name: string; color: string; min: number }>()
  included.forEach((d) => { const v = views.get(d.id)!; const c = byCat.get(v.category.name) ?? { name: v.category.name, color: v.category.color, min: 0 }; c.min += v.minutes ?? 0; byCat.set(v.category.name, c) })

  return (
    <>
      <PageHeader back={() => nav('/journal')} title={`Review ${drafts.length} ${drafts.length === 1 ? 'activity' : 'activities'}`}
        subtitle={<>From your {sourceLabel} entry · {weekdayShort(isoToLocal(entry.covers_start_at, tz).date)} {dayAndMonth(isoToLocal(entry.covers_start_at, tz).date)} · {formatClock(entry.covers_start_at, tz, fmt)} – {formatClock(entry.covers_end_at, tz, fmt)}</>}>
        <Button variant="subtle" icon="refresh" aria-label="Regenerate" onClick={() => setRegenOpen(true)}><span className="max-xl:sr-only">Regenerate</span></Button>
        <Button onClick={() => setDiscardOpen(true)}>Discard</Button>
        <Button variant="primary" icon="check" disabled={reasons.length > 0 || commit.isPending} loading={commit.isPending} onClick={save}
          title={reasons.length ? `To save: ${reasons.map((r) => r.text).join('; ')}` : undefined}>Save {count} {count === 1 ? 'activity' : 'activities'}</Button>
      </PageHeader>

      <div className="flex flex-col gap-4 p-4 md:px-7 md:py-[22px] md:pb-10">
        {stale && <p role="status" className="m-0 flex flex-wrap items-center gap-3 rounded-xl border border-warn/40 bg-warn/10 px-3.5 py-2.5 text-[13px]"><Icon name="alert" size={15} className="text-warn" /><span className="mr-auto">You edited the entry after this was read. These results may be out of date.</span><Button size="sm" loading={rerunning} onClick={() => onRerun(false)}>Read again</Button></p>}
        {later.length > 0 && (
          <p role="status" className="m-0 flex flex-wrap items-start gap-3 rounded-xl border border-accent/30 bg-tint px-3.5 py-2.5 text-[13px]">
            <Icon name="clock" size={15} className="mt-0.5 flex-none text-accent-ink" />
            <span className="min-w-0 flex-1"><b className="font-semibold">{later.length} later {later.length === 1 ? 'activity is' : 'activities are'} unticked.</b> {later.length === 1 ? 'It starts' : 'They start'} after this entry's window ends ({formatClock(entry.covers_end_at, tz, fmt)}), so {later.length === 1 ? 'it has' : 'they have'} not happened yet: {later.map((d) => views.get(d.id)?.title).slice(0, 4).join(', ')}{later.length > 4 ? '…' : ''}. Tick one here if it already happened.</span>
            <Button size="sm" onClick={() => setInclude((p) => ({ ...p, ...Object.fromEntries(later.map((d) => [d.id, true])) }))}>Tick them anyway</Button>
          </p>
        )}
        {reasons.length > 0 && (
          <div role="status" className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-warn/40 bg-warn/10 px-3.5 py-2.5 text-[13px]">
            <b className="font-semibold">To save:</b>
            {reasons.map((r) => <button key={r.text} type="button" className="font-medium text-accent-ink underline underline-offset-2" onClick={() => (r.to ? document.getElementById(r.to)?.scrollIntoView({ behavior: 'smooth', block: 'center' }) : undefined)}>{r.text}</button>)}
          </div>
        )}
        {review.warnings.map((w) => <p key={w} className="m-0 flex items-start gap-2 rounded-xl bg-tint px-3.5 py-2.5 text-[12.5px] text-muted"><Icon name="info" size={15} className="mt-px flex-none text-accent-ink" />{w}</p>)}

        {err && <p role="alert" className="m-0 flex items-start gap-2 rounded-xl border border-bad/40 bg-bad/10 px-3.5 py-2.5 text-[13px] font-medium"><Icon name="alert" size={15} className="mt-px flex-none text-bad" />{err}</p>}
        <section className="card p-[18px]" aria-label="Summary">
          <dl className="m-0 mb-4 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
            {[
              ['Activities', `${count}`], ['Covered', hm(coveredMin)], ['Not mentioned', hm(notMentioned)], ['Gaps', `${review.summary.gap_count}`],
              ['To double-check', `${included.filter((d) => d.band !== 'high' || d.flags.length).length}`], ['Tags applied', `${tagCount}`],
            ].map(([l, v]) => <div key={l}><dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">{l}</dt><dd className="num m-0 mt-1 text-[22px] font-semibold leading-none">{v}</dd></div>)}
          </dl>
          <div className="relative h-[30px] overflow-hidden rounded-lg bg-line2" role="img" aria-label={`${count} activities covering ${hm(coveredMin)} of ${hm(Math.round(span / 60000))}`}>
            {review.gaps.map((g) => <i key={g.start_at} className="hatch-bad absolute inset-y-0 block border-x border-dashed border-bad/60" style={{ left: `${pct(g.start_at)}%`, width: `${pct(g.end_at) - pct(g.start_at)}%` }} />)}
            {placed.map((d) => <i key={d.id} onMouseEnter={() => setHot(d.id)} onMouseLeave={() => setHot(undefined)} title={`${views.get(d.id)!.title} · ${hm(views.get(d.id)!.minutes ?? 0)}`} className={clsx('absolute inset-y-0 block border-r border-card transition', hot === d.id && 'brightness-110 ring-2 ring-inset ring-ink/40')} style={{ left: `${pct(d.start_at!)}%`, width: `${pct(d.end_at!) - pct(d.start_at!)}%`, background: views.get(d.id)!.category.color }} />)}
          </div>
          <div className="mt-1.5 flex justify-between text-[10.5px] font-medium text-faint" aria-hidden>{[0, 0.25, 0.5, 0.75, 1].map((f) => <span key={f}>{formatClock(new Date(w0 + span * f).toISOString(), tz, fmt)}</span>)}</div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted"><span className="flex items-center gap-1.5"><i className="size-2.5 rounded-[3px] bg-accent" />Logged by this entry</span><span className="flex items-center gap-1.5"><i className="hatch-bad size-2.5 rounded-[3px] border border-dashed border-bad" />Not mentioned</span>{unplacedMin > 0 && <span>{hm(unplacedMin)} has no fixed time</span>}</div>
        </section>

        {openQuestions.length > 0 && (
          <section id="questions" className="card border-accent/40 p-[18px]" aria-label="Questions" aria-live="polite">
            <h2 className="m-0 mb-1 flex items-center gap-2 text-sm font-semibold"><Icon name="sparkle" size={15} className="text-accent-ink" />A quick question{openQuestions.length > 1 ? 's' : ''} before saving</h2>
            <p className="m-0 mb-3 text-xs text-muted">Cadence will not guess these. Your answer places the activity.</p>
            <ul className="m-0 flex list-none flex-col gap-3.5 p-0">
              {openQuestions.map((q) => (
                <li key={q.id}><p className="m-0 mb-2 text-[13px] font-semibold">{q.prompt}</p>
                  <div className="flex flex-wrap gap-2">{q.options.map((o) => <Button key={o.value} size="sm" disabled={answer.isPending} onClick={() => answer.mutate({ job_id: jobId, question_id: q.id, value: o.value }, { onError: (e) => toast.error(errorMessage(e)) })}>{o.label}</Button>)}</div></li>
              ))}
            </ul>
          </section>
        )}

        {review.replace_candidates.length > 0 && (
          <section className="card p-[18px]" aria-label="Earlier activities from this entry">
            <h2 className="m-0 mb-1 text-sm font-semibold">This entry already has {review.replace_candidates.length} saved {review.replace_candidates.length === 1 ? 'activity' : 'activities'}</h2>
            <p className="m-0 mb-3 text-xs text-muted">{review.replace_candidates.map((c) => c.title).slice(0, 4).join(', ')}{review.replace_candidates.length > 4 ? '…' : ''}</p>
            <div role="radiogroup" aria-label="What to do with them" className="flex flex-wrap gap-2">
              {([[true, 'Replace them with these'], [false, 'Keep both']] as const).map(([v, l]) => <button key={l} type="button" role="radio" aria-checked={replacePrev === v} onClick={() => setReplacePrev(v)} className={clsx('h-8 rounded-full border px-3.5 text-[12.5px]', replacePrev === v ? 'border-accent bg-tint font-semibold text-accent-ink' : 'border-line text-muted hover:text-ink')}>{l}</button>)}
            </div>
            {replacePrev && review.replace_candidates.some((c) => c.user_edited) && <p className="m-0 mt-2 text-xs text-faint">Ones you edited by hand are kept.</p>}
          </section>
        )}

        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <div className="flex min-w-0 flex-col gap-3" aria-label="Activities">
            {drafts.length === 0 && <EmptyState icon="info" title="Nothing found in this entry">Add a few specifics like what you did and roughly when, then regenerate.</EmptyState>}
            {rows.map((r) => r.kind === 'draft'
              ? <DraftCard key={r.d.id} d={r.d} idx={r.i} view={views.get(r.d.id)!} included={isIn(r.d.id)} hot={hot === r.d.id} blockers={blockersOf(r.d.id)} tz={tz} fmt={fmt}
                  conflicts={review.conflicts.filter((c) => c.draft_id === r.d.id)} resolution={resolutions[r.d.id]?.action}
                  onInclude={(v) => setInclude((p) => ({ ...p, [r.d.id]: v }))} onHover={(on) => setHot(on ? r.d.id : undefined)} onEdit={() => setEditing(r.d.id)}
                  onRemoveTag={(key) => setEdits((p) => { const e = p[r.d.id] ?? initialEdit(r.d, tz); return { ...p, [r.d.id]: key.startsWith('new:') ? { ...e, removedNew: [...e.removedNew, key.slice(4)] } : { ...e, tag_ids: e.tag_ids.filter((x) => x !== key) } } })}
                  onResolve={(c, a) => setResolutions((p) => ({ ...p, [r.d.id]: { action: a, existing: c.other_id } }))} />
              : <GapRow key={r.g.start_at} minutes={r.g.minutes} label={gapLabel(r.g)} marked={transitions.includes(r.g.start_at)}
                  onTransition={() => setTransitions((p) => (p.includes(r.g.start_at) ? p.filter((x) => x !== r.g.start_at) : [...p, r.g.start_at]))}
                  onAdd={() => { const a = isoToLocal(r.g.start_at, tz), b = isoToLocal(r.g.end_at, tz); setAddGap({ date: a.date, start: a.time, end: b.time }) }} />)}
          </div>

          <aside className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-4" aria-label="Context">
            <section className="card p-[18px]">
              <h3 className="m-0 mb-2.5 text-sm font-semibold">What you said</h3>
              <p className="m-0 max-h-[320px] overflow-y-auto whitespace-pre-wrap text-[13px] leading-[1.7] text-muted">{segs}</p>
            </section>
            <section className="card p-[18px]">
              <h3 className="m-0 mb-2.5 text-sm font-semibold">From this entry</h3>
              <div className="flex h-3 overflow-hidden rounded-md bg-line2" role="img" aria-label="Time by category">{[...byCat.values()].map((c) => <i key={c.name} className="block h-full" style={{ width: `${(c.min / total) * 100}%`, background: c.color }} />)}</div>
              <ul className="m-0 mt-3 flex list-none flex-col gap-1.5 p-0 text-[12.5px]">{[...byCat.values()].sort((a, b) => b.min - a.min).map((c) => <li key={c.name} className="flex items-center gap-2"><i className="size-2.5 rounded-[3px]" style={{ background: c.color }} />{c.name}<b className="num ml-auto font-semibold">{hm(c.min)}</b></li>)}
                {byCat.size === 0 && <li className="text-muted">Nothing selected.</li>}</ul>
            </section>
            {review.ideal && review.ideal.rows.length > 0 && (
              <section className="card p-[18px]">
                <h3 className="m-0 mb-1 text-sm font-semibold">Today vs your Ideal day</h3>
                <p className="m-0 mb-3 text-xs text-muted">{dayAndMonth(review.ideal.date)} so far, with this entry</p>
                <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
                  {review.ideal.rows.map((r) => {
                    const max = Math.max(r.target, r.actual, 1)
                    return <li key={r.category_id} className="grid grid-cols-[96px_minmax(0,1fr)_92px] items-center gap-2.5 text-xs">
                      <span className="flex min-w-0 items-center gap-1.5"><i className="size-2 flex-none rounded-[2px]" style={{ background: r.color }} /><span className="truncate">{r.name}</span></span>
                      <span className="relative h-2.5 rounded-[5px] bg-line2" role="img" aria-label={`${hm(r.actual)} of ${hm(r.target)}`}><i className="absolute inset-y-0 left-0 rounded-[5px]" style={{ width: `${(r.actual / max) * 100}%`, background: r.color }} /><em className="absolute -inset-y-[3px] w-0.5 rounded-sm bg-ink" style={{ left: `${(r.target / max) * 100}%` }} /></span>
                      <span className="num text-right font-semibold">{hm(r.actual)} <span className="font-medium text-faint">/ {hm(r.target)}</span></span></li>
                  })}
                </ul>
              </section>
            )}
          </aside>
        </div>
      </div>

      <DraftEditDialog draft={editingDraft} value={editingDraft ? getEdit(editingDraft) : null} tz={tz} onClose={() => setEditing(undefined)} onSave={(e) => { setEdits((p) => ({ ...p, [editing!]: e })); setEditing(undefined) }} />
      <ActivityFormDialog open={!!addGap} onOpenChange={(o) => !o && setAddGap(undefined)} defaults={addGap} />
      <Dialog open={regenOpen} onOpenChange={setRegenOpen} title="Read this entry again" description="Your edits on this screen are discarded. You can give Cadence a hint about what to change."
        footer={<><Button variant="subtle" onClick={() => setRegenOpen(false)}>Cancel</Button><Button variant="primary" loading={rerunning} onClick={() => { setRegenOpen(false); onRerun(true, hint.trim() || undefined) }}>Regenerate</Button></>}>
        <label className="flex flex-col gap-1.5 text-xs font-semibold text-muted">Hint (optional)
          <Textarea rows={3} maxLength={500} value={hint} onChange={(e) => setHint(e.target.value)} placeholder="e.g. “Lunch was at 1pm, not noon.”" /></label>
      </Dialog>
      <Dialog open={discardOpen} onOpenChange={setDiscardOpen} title="Leave without saving?" description="Nothing is added to your Calendar. The entry stays in your Journal so you can come back to this review."
        footer={<><Button variant="subtle" onClick={() => setDiscardOpen(false)}>Keep reviewing</Button><Button variant="danger" onClick={() => nav('/journal')}>Discard</Button></>}><span className="text-[13px] text-muted">Your answers and edits on this screen will be lost.</span></Dialog>
    </>
  )
}
