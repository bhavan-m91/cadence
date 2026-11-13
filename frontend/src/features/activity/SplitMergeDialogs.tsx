import { useState } from 'react'
import { errorMessage } from '@/api/errors'
import { useMergeActivities, useSplitActivity } from '@/api/hooks/useActivities'
import type { Activity } from '@/api/types'
import { CategorySelect } from '@/components/domain/Pickers'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Field, Input } from '@/components/ui/Field'
import { hm, isoToLocal, localToIso, minutesBetween, snap } from '@/lib/time'
import { useAuthStore } from '@/stores/authStore'
import { toast } from '@/stores/toastStore'

export function SplitDialog({ activity, open, onOpenChange }: { activity: Activity; open: boolean; onOpenChange: (v: boolean) => void }) {
  const tz = useAuthStore((s) => s.user!.timezone)
  const split = useSplitActivity()
  const mid = new Date(Date.parse(activity.start_at!) + (snap(activity.duration_minutes! / 2) || 5) * 60000).toISOString()
  const [time, setTime] = useState(isoToLocal(mid, tz).time)
  const [error, setError] = useState<string>()
  const day = isoToLocal(activity.start_at!, tz).date
  // A block that crosses midnight: assume the split time is on the start date unless that falls outside the block.
  let at = localToIso(day, time, tz)
  if (Date.parse(at) <= Date.parse(activity.start_at!)) at = localToIso(isoToLocal(activity.end_at!, tz).date, time, tz)
  const a = minutesBetween(activity.start_at!, at), b = minutesBetween(at, activity.end_at!)
  const valid = a >= 5 && b >= 5
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Split activity" description="Cuts one block into two at a time. Category, tags and task are copied to both."
      footer={<><Button variant="subtle" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="primary" disabled={!valid} loading={split.isPending}
        onClick={() => split.mutate({ id: activity.id, at }, { onSuccess: () => { toast.success('Split into two activities'); onOpenChange(false) }, onError: (e) => setError(errorMessage(e)) })}>Split</Button></>}>
      <div className="flex flex-col gap-4">
        <Field label="Split at">{(id) => <Input id={id} dense type="time" step={300} value={time} onChange={(e) => setTime(e.target.value)} />}</Field>
        <p className={`text-sm ${valid ? 'text-muted' : 'text-bad'}`} role={valid ? undefined : 'alert'}>
          {valid ? <>Part 1 <b className="num text-ink">{hm(a)}</b> · Part 2 <b className="num text-ink">{hm(b)}</b></> : 'Each part must be at least 5 minutes.'}
        </p>
        {error && <p role="alert" className="text-[13px] text-bad">{error}</p>}
      </div>
    </Dialog>
  )
}

export function MergeDialog({ first, second, open, onOpenChange, onDone }: { first: Activity; second: Activity; open: boolean; onOpenChange: (v: boolean) => void; onDone: (survivorId: string) => void }) {
  const merge = useMergeActivities()
  const [pair] = useState([first, second].sort((x, y) => Date.parse(x.start_at!) - Date.parse(y.start_at!)))
  const differ = first.category.id !== second.category.id
  const [category, setCategory] = useState(pair[0].category.id)
  const [title, setTitle] = useState(pair[0].title)
  const [error, setError] = useState<string>()
  const total = minutesBetween(pair[0].start_at!, pair[1].end_at!)
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Merge activities" description="Joins two back-to-back activities into one. Tags are combined."
      footer={<><Button variant="subtle" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="primary" loading={merge.isPending}
        onClick={() => merge.mutate({ activity_ids: pair.map((a) => a.id), title, category_id: differ ? category : undefined }, { onSuccess: (a) => { toast.success('Merged'); onDone(a.id); onOpenChange(false) }, onError: (e) => setError(errorMessage(e)) })}>Merge into {hm(total)}</Button></>}>
      <div className="flex flex-col gap-4">
        <ul className="flex flex-col gap-1.5 text-[13px]">{pair.map((a) => <li key={a.id} className="flex justify-between rounded-lg bg-line2 px-3 py-2"><span className="font-medium">{a.title}</span><span className="num text-muted">{hm(a.duration_minutes!)}</span></li>)}</ul>
        <Field label="Title">{(id) => <Input id={id} dense value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} />}</Field>
        {differ && <Field label="Category" hint="These two have different categories. Pick the one to keep.">{(id) => <CategorySelect id={id} dense value={category} onChange={setCategory} />}</Field>}
        {error && <p role="alert" className="text-[13px] text-bad">{error}</p>}
      </div>
    </Dialog>
  )
}
