import clsx from 'clsx'
import { useEffect, useState } from 'react'
import type { ReviewConflict, ReviewDraft } from '@/api/types'
import { CategoryChip, TagChip } from '@/components/domain/Chips'
import { CategorySelect, TagPicker, TaskSelect } from '@/components/domain/Pickers'
import { isoToRange, rangeMinutes, TimeRangeInput, type RangeValue } from '@/components/domain/TimeRangeInput'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Field, Input, Textarea } from '@/components/ui/Field'
import { Icon } from '@/components/ui/Icon'
import { formatRange, hm, type TimeFormat } from '@/lib/time'

export interface DraftEdit {
  title: string; description: string; category_id: string; tag_ids: string[]; removedNew: string[]
  range: RangeValue | null; duration: number | null; task_id: string; new_task_title: string
}

export const initialEdit = (d: ReviewDraft, tz: string): DraftEdit => ({
  title: d.title, description: d.description ?? '', category_id: d.category.id,
  tag_ids: d.tags.filter((t) => t.applied && t.tag_id).map((t) => t.tag_id!), removedNew: [],
  range: d.placement === 'placed' && d.start_at && d.end_at ? isoToRange(d.start_at, d.end_at, tz) : null,
  duration: d.duration_minutes, task_id: d.task.task_id ?? '', new_task_title: d.task.new_task_title ?? '',
})

/** Starts at or after the end of the entry's window: it has not happened yet, so it is a plan rather than something to log. */
export function isLater(d: ReviewDraft, windowEndIso: string): boolean {
  const at = d.placement === 'placed' ? d.start_at : d.window_start_at
  return !!at && Date.parse(at) >= Date.parse(windowEndIso)
}

export type ResolutionAction = 'trim_new' | 'trim_existing' | 'replace_existing' | 'keep_unplaced'

const FLAG_TEXT: Record<string, string> = {
  start_unknown: 'No start time was given.', unplaced: 'No fixed time. It is kept as “some time” in the window.', duration_estimated: 'The duration was estimated.',
  estimated: 'The time was inferred from your wording.', inferred: 'The time was inferred from your wording.', boundary_inferred: 'The start or end was inferred from the neighbouring activity.',
  meridiem_ambiguous: 'am or pm was unclear.', meridiem_inferred: 'am or pm was inferred.', outside_window: 'Falls outside the window you set.', extends_past_window: 'Runs past the end of the window.',
  after_window: 'Later than this entry\'s window, so it has not happened yet.',
  possible_duplicate: 'Might repeat something already logged.', quote_unverified: 'Could not match this to your words.', category_unresolved: 'The category is a best guess.',
  time_unsupported: 'The time is not clearly in your words.', missing_duration: 'No duration was given.',
}
export const flagText = (f: string) => FLAG_TEXT[f] ?? (f.charAt(0).toUpperCase() + f.slice(1).toLowerCase().replace(/_/g, ' ') + '.')

export interface DraftView {
  title: string; description: string; category: { name: string; color: string }
  tags: { key: string; name: string; color: string; source: string; isNew: boolean; needsCheck: boolean; removable: boolean }[]
  minutes: number | null; taskLabel: string | null
}

interface CardProps {
  d: ReviewDraft; idx: number; view: DraftView; included: boolean; hot: boolean; blockers: string[]
  conflicts: ReviewConflict[]; resolution?: ResolutionAction; tz: string; fmt: TimeFormat
  onInclude: (v: boolean) => void; onHover: (on: boolean) => void; onEdit: () => void; onRemoveTag: (key: string) => void
  onResolve: (c: ReviewConflict, a: ResolutionAction) => void
}

const when = (d: ReviewDraft, tz: string, fmt: TimeFormat) =>
  d.placement === 'placed' && d.start_at && d.end_at ? formatRange(d.start_at, d.end_at, tz, fmt)
    : d.window_start_at && d.window_end_at ? `Some time ${formatRange(d.window_start_at, d.window_end_at, tz, fmt)}` : 'Time not set'

export function DraftCard({ d, idx, view, included, hot, blockers, conflicts, resolution, tz, fmt, onInclude, onHover, onEdit, onRemoveTag, onResolve }: CardProps) {
  const warn = included && (blockers.length > 0 || d.band !== 'high' || d.flags.length > 0 || !!d.duplicate_of)
  const flags = [...(d.duplicate_of ? [`Looks like “${d.duplicate_of.title}”, which is already logged.`] : []), ...d.flags.filter((f) => f !== 'possible_duplicate' || !d.duplicate_of).map(flagText)]
  return (
    <article id={`draft-${d.id}`} onMouseEnter={() => onHover(true)} onMouseLeave={() => onHover(false)} onFocus={() => onHover(true)} onBlur={() => onHover(false)}
      className={clsx('grid grid-cols-[auto_minmax(0,1fr)_auto] gap-x-3 gap-y-2 rounded-[14px] border bg-card p-3.5 transition', warn ? 'border-warn/60' : 'border-line', hot && 'ring-2 ring-accent/40', !included && 'opacity-45')}>
      <label className="flex h-[22px] cursor-pointer items-center"><input type="checkbox" className="peer sr-only" checked={included} onChange={(e) => onInclude(e.target.checked)} aria-label={`Include ${view.title}`} />
        <span className="flex size-[22px] items-center justify-center rounded-[7px] border-2 border-ghostline text-white transition peer-checked:border-accent peer-checked:bg-accent peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent">{included && <Icon name="check" size={13} strokeWidth={3} />}</span></label>
      <div className="min-w-0">
        <div className="flex items-baseline gap-2"><span className="num text-[11px] font-semibold text-faint">{idx + 1}</span><h3 className="m-0 truncate text-sm font-semibold">{view.title}</h3></div>
        <div className="mt-0.5 flex items-center gap-1.5 text-xs font-medium text-muted"><Icon name="clock" size={12} />{when(d, tz, fmt)}</div>
      </div>
      <div className="flex items-start gap-2">
        <span className="num pt-px text-base font-semibold">{view.minutes ? hm(view.minutes) : '–'}</span>
        <button type="button" onClick={onEdit} aria-label={`Edit ${view.title}`} title="Edit" className="flex size-8 flex-none items-center justify-center rounded-lg border border-line text-muted hover:border-ghostline hover:text-ink"><Icon name="edit" size={14} /></button>
      </div>

      <div className="col-span-3 flex min-w-0 flex-col gap-2 pl-[34px] max-sm:pl-0">
        {view.description && <p className="m-0 text-[12.5px] leading-snug text-muted">{view.description}</p>}
        <div className="flex flex-wrap items-center gap-1.5">
          <CategoryChip name={view.category.name} color={view.category.color} />
          {view.taskLabel && <span className="inline-flex items-center gap-1 rounded-full bg-line2 px-2 py-0.5 text-[11px] font-semibold text-muted"><Icon name="tasks" size={11} />{view.taskLabel}</span>}
          {view.tags.map((t) => <span key={t.key} title={t.isNew ? 'New tag. It is created when you save.' : undefined}><TagChip name={t.name} color={t.color} source={t.source} needsCheck={t.needsCheck} onRemove={t.removable ? () => onRemoveTag(t.key) : undefined} /></span>)}
          <button type="button" onClick={onEdit} className="h-[22px] rounded-full border border-dashed border-ghostline px-2 text-[11px] font-semibold text-muted hover:text-ink">+ tag</button>
        </div>
        {included && flags.map((f) => <p key={f} className="m-0 flex items-start gap-1.5 text-xs font-medium text-warn"><Icon name="alert" size={13} className="mt-px flex-none" /><span className="text-ink/80">{f}</span></p>)}
        {included && blockers.includes('UNANSWERED_QUESTION') && <p className="m-0 text-xs font-semibold text-bad">Answer the question above to place this one.</p>}
        {included && blockers.includes('MISSING_DURATION') && <p className="m-0 text-xs font-semibold text-bad">Add a duration with Edit.</p>}
        {included && conflicts.map((c) => (
          <div key={c.other_id} role="group" aria-label="Resolve overlap" className="flex flex-col gap-2 rounded-[10px] border border-dashed border-bad/50 bg-bad/[.05] p-2.5">
            <p className="m-0 text-xs font-semibold">Overlaps “{c.other_title}” by {hm(c.overlap_minutes)}.</p>
            <div className="flex flex-wrap gap-1.5">
              {options(d, c).map(([a, l]) => (
                <button key={a} type="button" aria-pressed={resolution === a} onClick={() => onResolve(c, a)} className={clsx('h-7 rounded-full border px-3 text-[11.5px] font-semibold', resolution === a ? 'border-accent bg-tint text-accent-ink' : 'border-line bg-card text-muted hover:text-ink')}>{l}</button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </article>
  )
}

/** Shortening only works when the overlap touches an edge: an activity sitting in the middle of another cannot be trimmed into one piece. */
function options(d: ReviewDraft, c: ReviewConflict): [ResolutionAction, string][] {
  const touchStart = !!d.start_at && c.start_at === d.start_at, touchEnd = !!d.end_at && c.end_at === d.end_at
  const out: [ResolutionAction, string][] = []
  if (touchStart !== touchEnd) out.push(['trim_new', 'Shorten this one'])
  if (!c.other_is_draft) {
    if (touchStart || touchEnd) out.push(['trim_existing', 'Shorten the other'])
    out.push(['replace_existing', 'Replace the other'])
  }
  out.push(['keep_unplaced', 'Keep as “some time”'])
  return out
}

export function GapRow({ minutes, label, onAdd, onTransition, marked }: { minutes: number; label: string; onAdd: () => void; onTransition: () => void; marked: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-[12px] border border-dashed border-bad/50 px-3.5 py-2.5">
      <span className="hatch-bad h-6 w-9 flex-none rounded-md" aria-hidden />
      <div className="mr-auto min-w-0 text-xs"><b className="font-semibold">{marked ? 'Transition' : 'Not mentioned'}</b> · <span className="num font-semibold">{hm(minutes)}</span><span className="ml-1.5 text-faint">{label}</span></div>
      <Button size="sm" onClick={onAdd}>Add activity</Button>
      <Button size="sm" variant={marked ? 'primary' : 'ghost'} aria-pressed={marked} onClick={onTransition}>{marked ? 'Marked as transition' : 'Mark as transition'}</Button>
    </div>
  )
}

export function DraftEditDialog({ draft, value, tz, onClose, onSave }: { draft: ReviewDraft | null; value: DraftEdit | null; tz: string; onClose: () => void; onSave: (e: DraftEdit) => void }) {
  const [e, setE] = useState<DraftEdit | null>(value)
  useEffect(() => setE(value), [value])
  if (!draft || !e) return <Dialog open={false} onOpenChange={onClose} title="Edit activity"><span /></Dialog>
  const placed = e.range !== null
  const mins = placed ? rangeMinutes(e.range!, tz) : (e.duration ?? 0)
  const err = !e.title.trim() ? 'Give it a title.' : mins <= 0 ? (placed ? 'The end must come after the start.' : 'Enter a duration.') : mins > 1440 ? 'At most 24 hours.' : undefined
  const set = (p: Partial<DraftEdit>) => setE({ ...e, ...p })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title="Edit activity" description="Changes apply when you save the review." wide
      footer={<><Button variant="subtle" onClick={onClose}>Cancel</Button><Button variant="primary" disabled={!!err} title={err} onClick={() => onSave({ ...e, title: e.title.trim() })}>Done</Button></>}>
      <div className="flex flex-col gap-4">
        <Field label="Title" error={!e.title.trim() ? 'Give it a title.' : undefined}>{(id) => <Input id={id} dense value={e.title} maxLength={120} invalid={!e.title.trim()} onChange={(ev) => set({ title: ev.target.value })} />}</Field>
        <Field label="Notes">{(id) => <Textarea id={id} rows={2} value={e.description} maxLength={2000} onChange={(ev) => set({ description: ev.target.value })} />}</Field>
        <Field label="Category">{(id) => <CategorySelect id={id} dense value={e.category_id} onChange={(v) => set({ category_id: v })} />}</Field>
        {placed
          ? <div><div className="mb-1.5 text-xs font-semibold text-muted">When</div><TimeRangeInput value={e.range!} onChange={(v) => set({ range: v })} tz={tz} error={err && err.includes('end') ? err : undefined} /></div>
          : <Field label="Duration (minutes)" hint="No start time was given, so only the length is needed." error={err && !err.includes('title') ? err : undefined}>{(id) => <Input id={id} dense type="number" min={5} step={5} max={1440} value={e.duration ?? ''} onChange={(ev) => set({ duration: ev.target.value ? Number(ev.target.value) : null })} />}</Field>}
        <div><div className="mb-1.5 text-xs font-semibold text-muted">Tags</div><TagPicker value={e.tag_ids} onChange={(ids) => set({ tag_ids: ids })} /></div>
        <Field label="Task" hint="Link an existing task, or name a new one.">{(id) => (
          <div className="flex flex-col gap-2"><TaskSelect id={id} value={e.task_id} onChange={(v) => set({ task_id: v, new_task_title: '' })} />
            {!e.task_id && <Input dense aria-label="New task title" placeholder="…or a new task title" maxLength={160} value={e.new_task_title} onChange={(ev) => set({ new_task_title: ev.target.value })} />}</div>
        )}</Field>
      </div>
    </Dialog>
  )
}
