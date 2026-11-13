import { addDays, daysBetween, isoToLocal, localToIso, minutesBetween } from '@/lib/time'
import { Input } from '../ui/Field'

export interface RangeValue { date: string; start: string; end: string }

/** `end <= start` means the activity crosses midnight (end is on the next day), as with sleep. */
export function rangeToIso(v: RangeValue, tz: string): { start_at: string; end_at: string } {
  const start_at = localToIso(v.date, v.start, tz)
  let end_at = localToIso(v.date, v.end, tz)
  if (Date.parse(end_at) <= Date.parse(start_at)) end_at = localToIso(addDays(v.date, 1), v.end, tz)
  return { start_at, end_at }
}

export function isoToRange(startIso: string, endIso: string, tz: string): RangeValue {
  const s = isoToLocal(startIso, tz), e = isoToLocal(endIso, tz)
  return { date: s.date, start: s.time, end: e.time }
}

export function rangeMinutes(v: RangeValue, tz: string): number {
  const { start_at, end_at } = rangeToIso(v, tz)
  return minutesBetween(start_at, end_at)
}

export function TimeRangeInput({ value, onChange, tz, error }: { value: RangeValue; onChange: (v: RangeValue) => void; tz: string; error?: string }) {
  const { end_at, start_at } = rangeToIso(value, tz)
  const crosses = daysBetween(isoToLocal(start_at, tz).date, isoToLocal(end_at, tz).date) > 0
  return (
    <div>
      <div className="grid grid-cols-[1.4fr_1fr_1fr] gap-2">
        <label className="flex flex-col gap-1 text-xs font-semibold text-muted">Date
          <Input dense type="date" value={value.date} onChange={(e) => onChange({ ...value, date: e.target.value })} aria-invalid={!!error} />
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold text-muted">Start
          <Input dense type="time" step={300} value={value.start} onChange={(e) => onChange({ ...value, start: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold text-muted">End
          <Input dense type="time" step={300} value={value.end} onChange={(e) => onChange({ ...value, end: e.target.value })} />
        </label>
      </div>
      {crosses && <p className="mt-1.5 text-xs text-muted">Ends the next day.</p>}
      {error && <p role="alert" className="mt-1.5 text-xs text-bad">{error}</p>}
    </div>
  )
}
