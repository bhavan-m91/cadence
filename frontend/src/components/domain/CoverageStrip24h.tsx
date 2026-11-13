import { hm, formatRange, type TimeFormat } from '@/lib/time'
import type { DayTimeline } from '@/api/types'
import { Tooltip } from '../ui/Tooltip'

/** A day as a 24h bar: logged blocks by category, unlogged gaps hatched red (clicking a gap logs it). */
export function CoverageStrip24h({ day, tz, fmt = '12h', height = 22, onGap }: { day: DayTimeline; tz: string; fmt?: TimeFormat; height?: number; onGap?: (g: DayTimeline['gaps'][number]) => void }) {
  const start = Date.parse(day.day_start_at)
  const total = Date.parse(day.day_end_at) - start
  const pos = (iso: string) => ((Date.parse(iso) - start) / total) * 100
  return (
    <div className="relative w-full overflow-hidden rounded-md bg-line2" style={{ height }} role="img" aria-label={`Logged ${hm(day.coverage.logged)} of ${hm(day.coverage.elapsed || 1440)}, ${day.gaps.length} gaps`}>
      {day.blocks.map((b) => (
        <Tooltip key={b.id + b.start_at} content={<><b>{b.title}</b><br />{formatRange(b.start_at, b.end_at, tz, fmt)} · {hm(b.minutes)}<br />{b.category.path_names}</>}>
          <i className="absolute top-0 bottom-0 block border-r border-card" style={{ left: `${pos(b.start_at)}%`, width: `${pos(b.end_at) - pos(b.start_at)}%`, background: b.category.color }} />
        </Tooltip>
      ))}
      {day.gaps.map((g) => (
        <Tooltip key={g.start_at} content={<><b>Unlogged</b><br />{formatRange(g.start_at, g.end_at, tz, fmt)} · {hm(g.minutes)}{onGap && <><br />Click to log it</>}</>}>
          <button type="button" aria-label={`Unlogged ${hm(g.minutes)}, ${formatRange(g.start_at, g.end_at, tz, fmt)}`} onClick={() => onGap?.(g)}
            className="hatch-bad absolute top-0 bottom-0 block border-x border-dashed border-bad" style={{ left: `${pos(g.start_at)}%`, width: `${pos(g.end_at) - pos(g.start_at)}%`, cursor: onGap ? 'pointer' : 'default' }} />
        </Tooltip>
      ))}
    </div>
  )
}
