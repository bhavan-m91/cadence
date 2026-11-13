/** Timezone-aware time helpers. The server owns duration arithmetic; this only converts and formats (PRD 8.4). */
import { TZDate } from '@date-fns/tz'

export type TimeFormat = '12h' | '24h'

export const DAY_MS = 86_400_000

export function todayIn(tz: string, now: number = Date.now()): string {
  const d = new TZDate(now, tz)
  return ymd(d.getFullYear(), d.getMonth() + 1, d.getDate())
}

export function ymd(y: number, m: number, d: number): string {
  return `${y.toString().padStart(4, '0')}-${m.toString().padStart(2, '0')}-${d.toString().padStart(2, '0')}`
}

export function parseYmd(s: string): { y: number; m: number; d: number } {
  const [y, m, d] = s.split('-').map(Number)
  return { y, m, d }
}

/** Calendar arithmetic on plain dates (no timezone involved). */
export function addDays(date: string, n: number): string {
  const { y, m, d } = parseYmd(date)
  const t = new Date(Date.UTC(y, m - 1, d + n))
  return ymd(t.getUTCFullYear(), t.getUTCMonth() + 1, t.getUTCDate())
}

export function daysBetween(a: string, b: string): number {
  const pa = parseYmd(a), pb = parseYmd(b)
  return Math.round((Date.UTC(pb.y, pb.m - 1, pb.d) - Date.UTC(pa.y, pa.m - 1, pa.d)) / DAY_MS)
}

/** `weekStart`: 1 = Monday … 7 = Sunday (same convention as the API). */
export function weekStartOf(date: string, weekStart: number): string {
  const { y, m, d } = parseYmd(date)
  const iso = ((new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7) + 1
  return addDays(date, -((iso - weekStart + 7) % 7))
}

export function weekDates(date: string, weekStart: number): string[] {
  const s = weekStartOf(date, weekStart)
  return Array.from({ length: 7 }, (_, i) => addDays(s, i))
}

/** Local wall-clock time on a date in `tz` -> UTC ISO string. */
export function localToIso(date: string, hhmm: string, tz: string): string {
  const { y, m, d } = parseYmd(date)
  const [hh, mm] = hhmm.split(':').map(Number)
  // TZDate.toISOString() keeps the zone's offset; normalise to UTC so every instant we send looks the same.
  return new Date(new TZDate(y, m - 1, d, hh, mm, 0, tz).getTime()).toISOString()
}

export function isoToLocal(iso: string, tz: string): { date: string; time: string } {
  const d = new TZDate(iso, tz)
  return {
    date: ymd(d.getFullYear(), d.getMonth() + 1, d.getDate()),
    time: `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`,
  }
}

export function formatClock(iso: string, tz: string, fmt: TimeFormat = '12h'): string {
  const d = new TZDate(iso, tz)
  const h = d.getHours(), mi = d.getMinutes()
  if (fmt === '24h') return `${h.toString().padStart(2, '0')}:${mi.toString().padStart(2, '0')}`
  const suffix = h >= 12 ? 'pm' : 'am'
  const h12 = h % 12 === 0 ? 12 : h % 12
  return mi === 0 ? `${h12}${suffix}` : `${h12}:${mi.toString().padStart(2, '0')}${suffix}`
}

export function formatRange(startIso: string, endIso: string, tz: string, fmt: TimeFormat = '12h'): string {
  return `${formatClock(startIso, tz, fmt)} – ${formatClock(endIso, tz, fmt)}`
}

/** 150 -> "2h 30m", 45 -> "45m", 180 -> "3h". */
export function hm(minutes: number): string {
  const sign = minutes < 0 ? '-' : ''
  const m = Math.abs(Math.round(minutes))
  const h = Math.floor(m / 60), r = m % 60
  if (h === 0) return `${sign}${r}m`
  return r === 0 ? `${sign}${h}h` : `${sign}${h}h ${r}m`
}

export function minutesBetween(a: string, b: string): number {
  return Math.round((Date.parse(b) - Date.parse(a)) / 60000)
}

export function snap(minutes: number, step = 5): number {
  return Math.round(minutes / step) * step
}

const shortDay = new Intl.DateTimeFormat('en-US', { weekday: 'short', timeZone: 'UTC' })
const longDay = new Intl.DateTimeFormat('en-US', { weekday: 'long', timeZone: 'UTC' })
const dayMonth = new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const monthLong = new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' })

const asUtc = (date: string) => {
  const { y, m, d } = parseYmd(date)
  return new Date(Date.UTC(y, m - 1, d))
}
export const weekdayShort = (date: string) => shortDay.format(asUtc(date))
export const weekdayLong = (date: string) => longDay.format(asUtc(date))
export const dayAndMonth = (date: string) => dayMonth.format(asUtc(date))
export const monthYear = (date: string) => monthLong.format(asUtc(date))
export const dayOfMonth = (date: string) => parseYmd(date).d

export function rangeLabel(from: string, to: string): string {
  const a = parseYmd(from), b = parseYmd(to)
  if (a.m === b.m) return `${dayAndMonth(from)} – ${b.d}`
  return `${dayAndMonth(from)} – ${dayAndMonth(to)}`
}

export function greeting(tz: string, now: number = Date.now()): string {
  const h = new TZDate(now, tz).getHours()
  return h < 5 ? 'Good evening' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

export const COMMON_TIMEZONES = [
  'Asia/Kolkata', 'Asia/Dubai', 'Asia/Singapore', 'Asia/Tokyo', 'Australia/Sydney', 'Europe/London', 'Europe/Berlin', 'Europe/Paris',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'America/Sao_Paulo', 'Africa/Johannesburg', 'UTC',
]

export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata'
  } catch {
    return 'Asia/Kolkata'
  }
}

export function allTimezones(): string[] {
  try {
    const list = (Intl as any).supportedValuesOf?.('timeZone') as string[] | undefined
    if (list?.length) return list.includes('UTC') ? list : [...list, 'UTC']
  } catch {
    /* fall through */
  }
  return COMMON_TIMEZONES
}
