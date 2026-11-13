import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useDeleteEntry, useEntry, usePatchEntry, useProcessEntry, useRevisions } from '@/api/hooks/useJournal'
import { usePreferences } from '@/api/hooks/useSettings'
import { CategoryChip, TagChip } from '@/components/domain/Chips'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback'
import { Textarea } from '@/components/ui/Field'
import { Icon } from '@/components/ui/Icon'
import { dayAndMonth, formatClock, formatRange, hm, isoToLocal, weekdayLong } from '@/lib/time'
import { useAuthStore } from '@/stores/authStore'
import { toast } from '@/stores/toastStore'
import { STATUS_LABEL, statusTone } from './HistoryPage'
import clsx from 'clsx'

export function EntryPage() {
  const { entryId } = useParams()
  const nav = useNavigate()
  const tz = useAuthStore((s) => s.user!.timezone)
  const fmt = usePreferences().data?.time_format ?? '12h'
  const q = useEntry(entryId)
  const revs = useRevisions(entryId)
  const patch = usePatchEntry(), del = useDeleteEntry(), process = useProcessEntry()
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState('')
  const [delOpen, setDelOpen] = useState(false)
  const [keep, setKeep] = useState<'keep' | 'delete'>('keep')
  const [showRevs, setShowRevs] = useState(false)
  const e = q.data
  const earlier = (revs.data ?? []).filter((r) => r.revision !== e?.revision)
  useEffect(() => { if (e && !editing) setText(e.raw_text) }, [e, editing])

  const goBack = () => nav('/journal/history')
  if (q.error) return <><PageHeader title="Entry" back={goBack} /><ErrorState error={q.error} onRetry={() => q.refetch()} /></>
  if (!e) return <><PageHeader title="Entry" back={goBack} /><div className="p-4 md:px-7"><Skeleton className="h-64" /></div></>

  const when = isoToLocal(e.covers_start_at, tz).date
  const hasActs = e.activities.length > 0
  const saveText = async () => {
    try { await patch.mutateAsync({ id: e.id, version: e.version, raw_text: text.trim() }); setEditing(false); toast.success(hasActs ? 'Saved. Re-read the entry to refresh its activities.' : 'Saved.') }
    catch (err) { toast.error(err instanceof ApiError && err.code === 'VERSION_CONFLICT' ? 'This entry changed elsewhere. Reload and try again.' : errorMessage(err)) }
  }
  const reread = async () => {
    try { const j = await process.mutateAsync({ id: e.id, key: crypto.randomUUID(), regenerate: hasActs }); nav(`/journal/${e.id}/review?job=${j.job_id}`) }
    catch (err) { toast.error(errorMessage(err)) }
  }
  const remove = async () => {
    try { await del.mutateAsync({ id: e.id, activities: hasActs ? keep : undefined }); toast.success('Entry deleted.'); nav('/journal/history') } catch (err) { toast.error(errorMessage(err)) }
  }

  return (
    <>
      <PageHeader back={goBack} title={e.title ?? 'Journal entry'} subtitle={<>{weekdayLong(when)} {dayAndMonth(when)} · {formatClock(e.covers_start_at, tz, fmt)} – {formatClock(e.covers_end_at, tz, fmt)} · {e.input_method === 'dictated' ? 'dictated' : 'typed'}</>}>
        <span className={clsx('rounded-full px-2.5 py-1 text-[11.5px] font-semibold', statusTone(e.status))}>{STATUS_LABEL[e.status] ?? e.status}</span>
        {(e.status === 'review' || e.status === 'processing') && <Button variant="primary" onClick={() => nav(`/journal/${e.id}/review`)}>Continue review</Button>}
        {e.status !== 'review' && e.status !== 'processing' && <Button icon="sparkle" loading={process.isPending} onClick={reread}>{hasActs ? 'Re-read entry' : 'Read entry'}</Button>}
        <Button variant="subtle" icon="trash" onClick={() => setDelOpen(true)}>Delete</Button>
      </PageHeader>

      <div className="grid items-start gap-4 p-4 md:px-7 md:py-[22px] md:pb-10 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <section className="card p-[18px]" aria-labelledby="entry-text">
          <div className="mb-3 flex items-center justify-between gap-2"><h2 id="entry-text" className="m-0 text-sm font-semibold">Your entry</h2>
            {!editing ? <Button size="sm" icon="edit" onClick={() => setEditing(true)}>Edit text</Button> : <span className="flex gap-2"><Button size="sm" variant="subtle" onClick={() => { setEditing(false); setText(e.raw_text) }}>Cancel</Button><Button size="sm" variant="primary" loading={patch.isPending} disabled={!text.trim() || text.trim() === e.raw_text} onClick={saveText}>Save</Button></span>}</div>
          {editing ? <Textarea aria-label="Entry text" rows={12} maxLength={10000} value={text} onChange={(ev) => setText(ev.target.value)} className="min-h-[260px]" />
            : <p className="m-0 whitespace-pre-wrap text-sm leading-[1.7]">{e.raw_text}</p>}
          {editing && hasActs && <p className="m-0 mt-2 text-xs text-faint">Editing keeps the activities already saved. Re-read the entry afterwards to update them.</p>}
          {e.latest_job?.is_stale && !editing && <p role="status" className="m-0 mt-3 rounded-lg bg-warn/10 px-3 py-2 text-xs">The text changed after the last reading. Re-read the entry to refresh its activities.</p>}
          <div className="mt-3 border-t border-line2 pt-3">
            <button type="button" aria-expanded={showRevs} onClick={() => setShowRevs((v) => !v)} className="flex items-center gap-1.5 text-xs font-semibold text-muted hover:text-ink"><Icon name="history" size={14} />Earlier versions ({earlier.length})<Icon name="chevronDown" size={13} className={showRevs ? 'rotate-180' : ''} /></button>
            {showRevs && (
              <ol className="m-0 mt-2.5 flex list-none flex-col gap-2 p-0">
                {earlier.map((r) => <li key={r.revision} className="rounded-lg border border-line p-2.5 text-[12.5px]"><div className="mb-1 flex justify-between text-[11px] font-semibold text-faint"><span>Version {r.revision}</span><span>{dayAndMonth(isoToLocal(r.created_at, tz).date)} {formatClock(r.created_at, tz, fmt)}</span></div><p className="m-0 whitespace-pre-wrap text-muted">{r.raw_text}</p></li>)}
                {earlier.length === 0 && <li className="text-xs text-muted">This entry has not been edited.</li>}
              </ol>
            )}
          </div>
        </section>

        <section className="card p-[18px]" aria-labelledby="entry-acts">
          <h2 id="entry-acts" className="m-0 mb-3 text-sm font-semibold">Activities from this entry</h2>
          {!hasActs && <EmptyState icon="calendar" title="No activities yet">{e.status === 'confirmed' ? 'This entry did not create any activities.' : 'They appear here once you save the review.'}</EmptyState>}
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {e.activities.map((a) => (
              <li key={a.id}><Link to={`/activities/${a.id}`} className="flex flex-col gap-1.5 rounded-xl border border-line p-3 hover:border-ghostline">
                <span className="flex items-baseline justify-between gap-2"><b className="truncate text-[13px] font-semibold">{a.title}</b><span className="num flex-none text-[13px] font-semibold">{a.duration_minutes ? hm(a.duration_minutes) : '–'}</span></span>
                <span className="text-xs text-muted">{a.start_at && a.end_at ? formatRange(a.start_at, a.end_at, tz, fmt) : 'Some time that day'}</span>
                <span className="flex flex-wrap gap-1.5"><CategoryChip name={a.category.name} color={a.category.color} />{a.tags.map((t) => <TagChip key={t.name} name={t.name} color={t.color} source={t.source} />)}</span>
              </Link></li>
            ))}
          </ul>
        </section>
      </div>

      <Dialog open={delOpen} onOpenChange={setDelOpen} title="Delete this entry?" description="The text and its history are removed. This cannot be undone."
        footer={<><Button variant="subtle" onClick={() => setDelOpen(false)}>Cancel</Button><Button variant="danger" loading={del.isPending} onClick={remove}>Delete entry</Button></>}>
        {hasActs ? (
          <fieldset className="m-0 flex flex-col gap-2 border-0 p-0"><legend className="mb-2 text-[13px] text-muted">It created {e.activities.length} {e.activities.length === 1 ? 'activity' : 'activities'}. What should happen to them?</legend>
            {([['keep', 'Keep them on my Calendar'], ['delete', 'Delete them too']] as const).map(([v, l]) => <label key={v} className="flex items-center gap-2.5 text-sm"><input type="radio" name="keep" className="size-4 accent-[var(--accent)]" checked={keep === v} onChange={() => setKeep(v)} />{l}</label>)}</fieldset>
        ) : <span className="text-[13px] text-muted">Nothing else is affected.</span>}
      </Dialog>
    </>
  )
}
