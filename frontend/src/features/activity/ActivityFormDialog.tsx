import { useEffect, useMemo, useState } from 'react'
import { ApiError } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useCreateActivity, usePatchActivity, useSetActivityTags } from '@/api/hooks/useActivities'
import { flattenCategories, useCategories } from '@/api/hooks/useTaxonomy'
import type { Activity } from '@/api/types'
import { CategorySelect, ProjectSelect, TagPicker, TaskSelect } from '@/components/domain/Pickers'
import { isoToRange, rangeMinutes, rangeToIso, TimeRangeInput, type RangeValue } from '@/components/domain/TimeRangeInput'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Field, Input, Select, Textarea } from '@/components/ui/Field'
import { Segmented } from '@/components/layout/PageHeader'
import { hm, todayIn } from '@/lib/time'
import { useAuthStore } from '@/stores/authStore'
import { toast } from '@/stores/toastStore'

export interface FormDefaults { date?: string; start?: string; end?: string; kind?: 'actual' | 'planned' }

interface Props {
  open: boolean
  onOpenChange: (v: boolean) => void
  activity?: Activity | null
  defaults?: FormDefaults
}

const LOCATIONS = ['office', 'home', 'remote', 'travel', 'other'] as const

export function ActivityFormDialog({ open, onOpenChange, activity, defaults }: Props) {
  const tz = useAuthStore((s) => s.user!.timezone)
  const { data: tree } = useCategories()
  const create = useCreateActivity()
  const patch = usePatchActivity()
  const setTags = useSetActivityTags()
  const editing = !!activity

  const initial = useMemo(() => {
    const placed = !activity || activity.placement === 'placed'
    const range: RangeValue = activity?.start_at && activity.end_at
      ? isoToRange(activity.start_at, activity.end_at, tz)
      : activity?.window_start_at && activity.window_end_at ? isoToRange(activity.window_start_at, activity.window_end_at, tz)
      : { date: defaults?.date ?? todayIn(tz), start: defaults?.start ?? '09:00', end: defaults?.end ?? '10:00' }
    return {
      title: activity?.title ?? '', category_id: activity?.category.id ?? '', mode: (placed ? 'exact' : 'window') as 'exact' | 'window',
      range, duration: activity?.duration_minutes ?? 30, kind: (activity?.kind ?? defaults?.kind ?? 'actual') as 'actual' | 'planned',
      tagIds: activity?.tags.map((t) => t.tag_id) ?? [], taskId: activity?.task_id ?? '', projectId: activity?.project_id ?? '',
      location: activity?.location_type ?? '', description: activity?.description ?? '',
    }
  }, [activity, defaults, tz])

  const [f, setF] = useState(initial)
  const [error, setError] = useState<string>()
  useEffect(() => { if (open) { setF(initial); setError(undefined) } }, [open, initial])
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }))

  // Default the category once the tree has loaded (prefer a general work bucket).
  const flat = useMemo(() => flattenCategories(tree), [tree])
  useEffect(() => {
    if (open && !f.category_id && flat.length) set('category_id', (flat.find((c) => c.name === 'Deep work') ?? flat[0]).id)
  }, [open, flat, f.category_id]) // eslint-disable-line react-hooks/exhaustive-deps

  const minutes = rangeMinutes(f.range, tz)
  const busy = create.isPending || patch.isPending || setTags.isPending

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(undefined)
    const title = f.title.trim()
    if (!title) return setError('Give it a title.')
    if (!f.category_id) return setError('Choose a category.')
    if (f.mode === 'exact' && (minutes < 1 || minutes > 1440)) return setError('An activity must be between 1 minute and 24 hours.')
    const times = f.mode === 'exact'
      ? rangeToIso(f.range, tz)
      : { duration_minutes: Math.max(1, Number(f.duration) || 0), window_start_at: rangeToIso(f.range, tz).start_at, window_end_at: rangeToIso(f.range, tz).end_at }
    try {
      if (activity) {
        const clear: ('task_id' | 'project_id' | 'location_type' | 'description')[] = []
        if (!f.taskId && activity.task_id) clear.push('task_id')
        if (!f.projectId && activity.project_id) clear.push('project_id')
        if (!f.location && activity.location_type) clear.push('location_type')
        if (!f.description && activity.description) clear.push('description')
        await patch.mutateAsync({
          id: activity.id, version: activity.version, title, category_id: f.category_id, ...times,
          description: f.description || undefined, task_id: f.taskId || undefined, project_id: f.projectId || undefined,
          location_type: (f.location || undefined) as any, clear,
        })
        const before = activity.tags.map((t) => t.tag_id).sort().join()
        if (before !== [...f.tagIds].sort().join()) await setTags.mutateAsync({ id: activity.id, tag_ids: f.tagIds })
        toast.success('Activity updated')
      } else {
        await create.mutateAsync({
          title, category_id: f.category_id, tag_ids: f.tagIds, kind: f.kind, ...times,
          time_certainty: f.mode === 'window' ? 'estimated' : 'stated', description: f.description || undefined,
          task_id: f.taskId || undefined, project_id: f.projectId || undefined, location_type: (f.location || undefined) as any,
        })
        toast.success(f.kind === 'planned' ? 'Planned block added' : 'Time logged')
      }
      onOpenChange(false)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'ACTIVITY_OVERLAP') {
        const c = (err.details.conflicts ?? []) as { title: string; overlap_minutes: number }[]
        setError(c.length ? `Overlaps ${c.map((x) => `“${x.title}” by ${hm(x.overlap_minutes)}`).join(', ')}. Adjust the time.` : errorMessage(err))
      } else setError(errorMessage(err))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} wide title={editing ? 'Edit activity' : 'Log time'}
      description={editing ? 'Changes are saved to its history.' : 'Record what happened, or plan what is coming.'}
      footer={<><Button variant="subtle" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="primary" type="submit" form="activity-form" loading={busy}>{editing ? 'Save changes' : f.kind === 'planned' ? 'Add plan' : 'Log time'}</Button></>}>
      <form id="activity-form" onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <Field label="What was it?">{(id) => <Input id={id} dense autoFocus value={f.title} maxLength={120} placeholder="e.g. Fix sync bug in Product B" onChange={(e) => set('title', e.target.value)} />}</Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Category">{(id) => <CategorySelect id={id} dense value={f.category_id} onChange={(v) => set('category_id', v)} />}</Field>
          {!editing && <div className="flex flex-col gap-1.5"><span className="text-xs font-semibold text-muted">Type</span><Segmented label="Type" value={f.kind} onChange={(v) => set('kind', v)} options={[{ value: 'actual', label: 'Happened' }, { value: 'planned', label: 'Planned' }]} /></div>}
        </div>
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between"><span className="text-xs font-semibold text-muted">When</span>
            <Segmented label="Time precision" value={f.mode} onChange={(v) => set('mode', v)} options={[{ value: 'exact', label: 'Exact time' }, { value: 'window', label: 'Some time between' }]} />
          </div>
          <TimeRangeInput value={f.range} onChange={(v) => set('range', v)} tz={tz} />
          {f.mode === 'exact'
            ? <p className="text-xs text-muted">{minutes > 0 ? <>Duration <b className="num">{hm(minutes)}</b></> : 'End must be after start.'}</p>
            : <Field label="How long (minutes)" hint="Counts toward your totals but is not placed on the timeline.">{(id) => <Input id={id} dense type="number" min={1} max={1440} value={f.duration} onChange={(e) => set('duration', Number(e.target.value))} />}</Field>}
        </div>
        <Field label="Tags">{() => <TagPicker value={f.tagIds} onChange={(v) => set('tagIds', v)} />}</Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Task">{(id) => <TaskSelect id={id} value={f.taskId} onChange={(v) => set('taskId', v)} />}</Field>
          <Field label="Project">{(id) => <ProjectSelect id={id} dense value={f.projectId} onChange={(v) => set('projectId', v)} />}</Field>
          <Field label="Where">{(id) => <Select id={id} dense value={f.location} onChange={(e) => set('location', e.target.value)}><option value="">Not set</option>{LOCATIONS.map((l) => <option key={l} value={l}>{l[0].toUpperCase() + l.slice(1)}</option>)}</Select>}</Field>
        </div>
        <Field label="Notes">{(id) => <Textarea id={id} value={f.description} maxLength={2000} onChange={(e) => set('description', e.target.value)} />}</Field>
        {error && <p role="alert" className="rounded-lg bg-bad/10 px-3 py-2 text-[13px] text-bad">{error}</p>}
      </form>
    </Dialog>
  )
}
