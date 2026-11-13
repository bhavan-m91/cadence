import clsx from 'clsx'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useActivity, useActivityEvents, useDeleteActivity, useDuplicateActivity, useSetActivityTags } from '@/api/hooks/useActivities'
import { errorMessage } from '@/api/errors'
import type { Activity, DayTimeline } from '@/api/types'
import { CategoryChip, TagChip } from '@/components/domain/Chips'
import { TagPicker } from '@/components/domain/Pickers'
import { Button, IconButton } from '@/components/ui/Button'
import { ErrorState, Skeleton } from '@/components/ui/Feedback'
import { Icon } from '@/components/ui/Icon'
import { dayAndMonth, formatClock, formatRange, hm, isoToLocal, weekdayShort, type TimeFormat } from '@/lib/time'
import { useAuthStore } from '@/stores/authStore'
import { toast } from '@/stores/toastStore'
import { ActivityFormDialog } from './ActivityFormDialog'
import { MergeDialog, SplitDialog } from './SplitMergeDialogs'

const EVENT_LABEL: Record<string, string> = {
  created: 'Created', edited: 'Edited', tagged: 'Tags added', untagged: 'Tags removed', task_linked: 'Task linked', split: 'Split', merged: 'Merged',
  duplicated: 'Duplicated', approved: 'Approved', deleted: 'Deleted', restored: 'Restored',
}

function describeEvent(type: string, payload: Record<string, any> | null): string {
  if (!payload) return EVENT_LABEL[type] ?? type
  if (payload.tags) return `${EVENT_LABEL[type]}: ${(payload.tags as string[]).map((t) => `#${t}`).join(', ')}`
  if (payload.changes) return `Changed ${Object.keys(payload.changes).map((k) => k.replace('_id', '').replace('_', ' ')).join(', ')}`
  return EVENT_LABEL[type] ?? type
}

const Row = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="flex items-baseline justify-between gap-4 border-b border-line2 py-2 text-[13px] last:border-0"><dt className="text-muted">{label}</dt><dd className="m-0 text-right font-medium">{children}</dd></div>
)

/** Neighbours in the same day that can be merged with (back-to-back, within the gap rule). */
function neighbours(id: string, days: DayTimeline[] | undefined) {
  for (const d of days ?? []) {
    const i = d.blocks.findIndex((b) => b.id === id)
    if (i >= 0) return { prev: d.blocks[i - 1], next: d.blocks[i + 1] }
  }
  return {}
}

export function ActivityDetailPanel({ activityId, days, onClose, fmt }: { activityId: string; days?: DayTimeline[]; onClose: () => void; fmt: TimeFormat }) {
  const tz = useAuthStore((s) => s.user!.timezone)
  const nav = useNavigate()
  const { data: a, isLoading, error, refetch } = useActivity(activityId)
  const { data: events } = useActivityEvents(activityId)
  const del = useDeleteActivity()
  const dup = useDuplicateActivity()
  const setTags = useSetActivityTags()
  const [edit, setEdit] = useState(false)
  const [split, setSplit] = useState(false)
  const [mergeWith, setMergeWith] = useState<Activity | null>(null)
  const [editTags, setEditTags] = useState<string[] | null>(null)
  const { prev, next } = useMemo(() => neighbours(activityId, days), [activityId, days])

  return (
    <aside aria-label="Activity details" className="fixed inset-y-0 right-0 z-30 flex w-full max-w-[440px] flex-col border-l border-line bg-paper shadow-2xl">
      <div className="flex items-center justify-between border-b border-line bg-card px-4 py-3">
        <h2 className="m-0 text-sm font-semibold">Activity</h2>
        <IconButton icon="x" label="Close details" onClick={onClose} />
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading && <div className="flex flex-col gap-3"><Skeleton className="h-8 w-2/3" /><Skeleton className="h-24" /><Skeleton className="h-40" /></div>}
        {error && <ErrorState error={error} onRetry={() => refetch()} />}
        {a && (
          <div className="flex flex-col gap-4">
            <div>
              <h3 className="m-0 text-xl font-bold tracking-tighter2">{a.title}</h3>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <CategoryChip name={a.category.path_names} color={a.category.color} />
                {a.kind === 'planned' && <span className="rounded-full border border-dashed border-ghostline px-2 py-0.5 text-[11px] font-semibold text-muted">Planned</span>}
                {a.time_certainty !== 'stated' && <span className="rounded-full bg-line2 px-2 py-0.5 text-[11px] font-semibold text-muted" title="Time was estimated or inferred">~ {a.time_certainty}</span>}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" icon="edit" onClick={() => setEdit(true)}>Edit</Button>
              {a.placement === 'placed' && <Button size="sm" icon="split" onClick={() => setSplit(true)}>Split</Button>}
              <Button size="sm" icon="copy" loading={dup.isPending} onClick={() => dup.mutate({ id: a.id }, { onSuccess: (d) => { toast.success('Duplicated right after'); nav(`/activities/${d.id}`) }, onError: (e) => toast.error(errorMessage(e)) })}>Duplicate</Button>
              <Button size="sm" variant="ghost" icon="trash" className="text-bad" loading={del.isPending} onClick={() => del.mutate(a.id, { onSuccess: onClose, onError: (e) => toast.error(errorMessage(e)) })}>Delete</Button>
            </div>
            {a.placement === 'placed' && (prev || next) && (
              <div className="flex flex-wrap gap-2">
                {[prev && ['previous', prev] as const, next && ['next', next] as const].filter(Boolean).map((x) => {
                  const [label, b] = x as readonly ['previous' | 'next', typeof prev & {}]
                  return <Button key={b.id} size="sm" variant="subtle" icon="merge" onClick={() => {
                    const other = { ...a, id: b.id, title: b.title, start_at: b.start_at, end_at: b.end_at, duration_minutes: b.minutes, category: b.category } as Activity
                    setMergeWith(other)
                  }}>Merge with {label}</Button>
                })}
              </div>
            )}

            <section className="card p-4">
              <dl className="m-0">
                {a.placement === 'placed' ? (
                  <>
                    <Row label="When">{weekdayShort(isoToLocal(a.start_at!, tz).date)} {dayAndMonth(isoToLocal(a.start_at!, tz).date)} · {formatRange(a.start_at!, a.end_at!, tz, fmt)}</Row>
                    <Row label="Duration"><span className="num">{hm(a.duration_minutes!)}</span></Row>
                  </>
                ) : (
                  <>
                    <Row label="Some time between">{formatClock(a.window_start_at!, tz, fmt)} – {formatClock(a.window_end_at!, tz, fmt)}</Row>
                    <Row label="Duration"><span className="num">{hm(a.duration_minutes!)}</span> <span className="text-faint">(not placed)</span></Row>
                  </>
                )}
                <Row label="Category">{a.category.path_names}</Row>
                <Row label="Task">{a.task?.title ?? <span className="text-faint">None</span>}</Row>
                <Row label="Where">{a.location_type ? a.location_type[0].toUpperCase() + a.location_type.slice(1) : <span className="text-faint">Not set</span>}</Row>
                <Row label="Logged via">{a.origin === 'ai' ? 'Journal (AI)' : a.origin[0].toUpperCase() + a.origin.slice(1)}</Row>
                <Row label="Timezone">{a.timezone}</Row>
              </dl>
            </section>

            {a.description && <section className="card p-4"><h4 className="m-0 mb-1.5 text-[13px] font-semibold">Notes</h4><p className="m-0 whitespace-pre-wrap text-[13px] leading-relaxed text-muted">{a.description}</p></section>}

            <section className="card p-4">
              <div className="mb-2.5 flex items-center justify-between"><h4 className="m-0 text-[13px] font-semibold">Tags</h4>
                {editTags ? <span className="flex gap-1.5"><Button size="sm" variant="subtle" onClick={() => setEditTags(null)}>Cancel</Button><Button size="sm" variant="primary" loading={setTags.isPending} onClick={() => setTags.mutate({ id: a.id, tag_ids: editTags }, { onSuccess: () => setEditTags(null), onError: (e) => toast.error(errorMessage(e)) })}>Save</Button></span>
                  : <Button size="sm" variant="subtle" icon="edit" onClick={() => setEditTags(a.tags.map((t) => t.tag_id))}>Edit</Button>}
              </div>
              {editTags ? <TagPicker value={editTags} onChange={setEditTags} /> : (
                <div className="flex flex-wrap gap-1.5">{a.tags.length === 0 && <span className="text-xs text-faint">No tags</span>}{a.tags.map((t) => <TagChip key={t.tag_id} name={t.name} color={t.color} source={t.source} title={t.reason ?? undefined} />)}</div>
              )}
            </section>

            {a.source.quote && (
              <section className="card p-4"><h4 className="m-0 mb-1.5 text-[13px] font-semibold">Where it came from</h4>
                <p className="m-0 text-[13px] leading-relaxed text-muted">{a.source.context_before}<mark className="rounded bg-tint2 px-0.5 text-ink">{a.source.quote}</mark>{a.source.context_after}</p>
              </section>
            )}

            {a.also_tagged.length > 0 && (
              <section className="card p-4"><h4 className="m-0 mb-2 text-[13px] font-semibold">Also tagged this week</h4>
                <ul className="m-0 flex list-none flex-col gap-1 p-0">{a.also_tagged.map((o) => (
                  <li key={o.id}><button type="button" onClick={() => nav(`/activities/${o.id}`)} className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-line2"><span>{o.title}</span><span className="num text-muted">{o.duration_minutes ? hm(o.duration_minutes) : ''}</span></button></li>
                ))}</ul>
              </section>
            )}

            <section className="card p-4"><h4 className="m-0 mb-2 text-[13px] font-semibold">History</h4>
              <ol className="m-0 flex list-none flex-col gap-2.5 p-0">
                {(events ?? []).map((e, i) => (
                  <li key={e.id} className="flex gap-3 text-[13px]">
                    <span className={clsx('mt-1.5 size-2 flex-none rounded-full', i === (events!.length - 1) ? 'bg-accent' : 'bg-ghostline')} aria-hidden />
                    <div><div className="font-medium">{describeEvent(e.event_type, e.payload)}</div><div className="text-xs text-faint">{e.actor === 'user' ? 'You' : e.actor === 'ai' ? 'Cadence AI' : 'System'} · {new Date(e.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short', timeZone: tz })}</div></div>
                  </li>
                ))}
              </ol>
            </section>
          </div>
        )}
      </div>
      {a && <ActivityFormDialog open={edit} onOpenChange={setEdit} activity={a as unknown as Activity} />}
      {a && a.placement === 'placed' && split && <SplitDialog activity={a as unknown as Activity} open={split} onOpenChange={setSplit} />}
      {a && mergeWith && <MergeDialog first={a as unknown as Activity} second={mergeWith} open onOpenChange={(v) => !v && setMergeWith(null)} onDone={(id) => nav(`/activities/${id}`)} />}
      <span className="sr-only"><Icon name="info" /></span>
    </aside>
  )
}
