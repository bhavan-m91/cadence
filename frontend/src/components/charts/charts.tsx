import clsx from 'clsx'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { hm } from '@/lib/time'
import { Tooltip } from '../ui/Tooltip'
import { squarify } from './treemap'

/* Marks follow one spec everywhere: columns and bars <= 24px with a 4px rounded data end, lines 2px, markers >= 8px with a 2px surface ring,
   2px surface gaps between touching fills, hairline recessive grids. Text wears text tokens; the colour sits on a mark beside it. */

export function ChartTable({ caption, head, rows }: { caption: string; head: string[]; rows: ReactNode[][] }) {
  return (
    <details className="group mt-3 text-xs">
      <summary className="cursor-pointer select-none font-semibold text-muted hover:text-ink">View as table</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <caption className="sr-only">{caption}</caption>
          <thead><tr>{head.map((h, i) => <th key={h} scope="col" className={clsx('border-b border-line py-1.5 pr-3 text-[10.5px] font-semibold uppercase tracking-wide text-faint', i > 0 && 'text-right')}>{h}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={clsx('border-b border-line2 py-1.5 pr-3', j > 0 ? 'num text-right' : 'font-medium')}>{c}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </details>
  )
}

export function Legend({ items }: { items: { label: string; color: string; hatch?: boolean }[] }) {
  return (
    <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1.5 p-0 text-xs text-muted">
      {items.map((i) => <li key={i.label} className="flex items-center gap-1.5"><i className={clsx('size-2.5 rounded-[3px]', i.hatch && 'hatch-bad border border-dashed border-bad')} style={i.hatch ? undefined : { background: i.color }} />{i.label}</li>)}
    </ul>
  )
}

/** One whole split into parts (work vs personal). A bar, not a donut: the parts are read by length. */
export function SegmentedBar({ parts, format = hm }: { parts: { key: string; label: string; value: number; color: string }[]; format?: (n: number) => string }) {
  const total = parts.reduce((a, p) => a + p.value, 0)
  return (
    <div>
      <div className="flex h-9 gap-0.5 overflow-hidden rounded-lg" role="img" aria-label={parts.map((p) => `${p.label} ${format(p.value)}`).join(', ')}>
        {total === 0 ? <i className="block h-full w-full bg-line2" /> : parts.filter((p) => p.value > 0).map((p) => (
          <Tooltip key={p.key} content={<><b>{p.label}</b><br />{format(p.value)} · {Math.round((p.value / total) * 100)}%</>}>
            <i className="block h-full rounded-[4px] transition hover:brightness-110" style={{ width: `${(p.value / total) * 100}%`, background: p.color }} />
          </Tooltip>
        ))}
      </div>
      <ul className="m-0 mt-3 flex list-none flex-wrap gap-x-6 gap-y-2 p-0">
        {parts.map((p) => (
          <li key={p.key} className="flex items-center gap-2 text-[12.5px]"><i className="size-2.5 rounded-[3px]" style={{ background: p.color }} /><span className="text-muted">{p.label}</span><b className="num font-semibold">{format(p.value)}</b>{total > 0 && <span className="num text-faint">{Math.round((p.value / total) * 100)}%</span>}</li>
        ))}
      </ul>
    </div>
  )
}

export interface MeterItem { key: string; label: string; color: string; actual: number; target: number; expected?: number; status?: 'on_target' | 'under' | 'over'; hint?: string }
const STATUS = { on_target: ['On track', 'bg-good/15 text-good'], under: ['Behind', 'bg-warn/15 text-warn'], over: ['Ahead', 'bg-bad/15 text-bad'] } as const

/** A name, a bar and a figure per row, bars aligned. The tick is where you should be by now (or the full target). */
export function MeterList({ items, onOpen }: { items: MeterItem[]; onOpen?: (key: string) => void }) {
  const max = Math.max(1, ...items.map((i) => Math.max(i.actual, i.target)))
  return (
    <ul className="group/meters m-0 flex list-none flex-col gap-2.5 p-0">
      {items.map((i) => {
        const mark = i.expected ?? i.target
        const label = `${i.label}: ${hm(i.actual)} of ${hm(i.target)}${i.expected !== undefined ? `, expected ${hm(i.expected)} by now` : ''}`
        const st = i.status ? STATUS[i.status] : null
        return (
          <li key={i.key} className="transition-opacity group-hover/meters:opacity-35 hover:!opacity-100 focus-within:!opacity-100">
            <Tooltip content={<><b>{i.label}</b><br />Actual {hm(i.actual)}<br />Ideal {hm(i.target)}{i.expected !== undefined && <><br />By now {hm(i.expected)}</>}<br />{i.actual - mark >= 0 ? '+' : '−'}{hm(Math.abs(i.actual - mark))}</>}>
              <button type="button" disabled={!onOpen} onClick={() => onOpen?.(i.key)} aria-label={label} className="grid w-full grid-cols-[minmax(0,136px)_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-lg py-0.5 text-left enabled:hover:bg-line2/60 max-sm:grid-cols-[minmax(0,1fr)_auto]">
                <span className="flex min-w-0 items-center gap-2 text-[12.5px] font-medium"><i className="size-2.5 flex-none rounded-[3px]" style={{ background: i.color }} /><span className="truncate">{i.label}</span></span>
                <span className="relative h-2.5 rounded-[5px] bg-line2 max-sm:order-3 max-sm:col-span-2" aria-hidden>
                  <i className="absolute inset-y-0 left-0 rounded-[5px]" style={{ width: `${Math.min(100, (i.actual / max) * 100)}%`, background: i.color }} />
                  {i.target > 0 && <em className="absolute -inset-y-[3px] w-0.5 rounded-sm bg-ink" style={{ left: `calc(${Math.min(100, (mark / max) * 100)}% - 1px)` }} />}
                </span>
                <span className="flex items-center justify-end gap-2"><span className="num text-xs font-semibold">{hm(i.actual)} <span className="font-medium text-faint">/ {hm(i.expected ?? i.target)}</span></span>{st && <span className={clsx('hidden rounded-full px-2 py-0.5 text-[10.5px] font-semibold sm:inline', st[1])}>{st[0]}</span>}</span>
              </button>
            </Tooltip>
          </li>
        )
      })}
    </ul>
  )
}

export interface ColumnItem { key: string; label: string; sub?: string; value: number; color: string; flag?: boolean; muted?: boolean }

/** Columns from a single baseline with an optional target line. Capped at 24px so the band's leftover is air. */
export function Columns({ items, target, targetLabel, max, height = 150, format = hm, onOpen, valueLabels = true }: {
  items: ColumnItem[]; target?: number | null; targetLabel?: string; max?: number; height?: number; format?: (n: number) => string; onOpen?: (key: string) => void; valueLabels?: boolean
}) {
  const top = Math.max(1, max ?? 0, target ?? 0, ...items.map((i) => i.value)) * 1.08
  return (
    <div className="group/cols relative" style={{ paddingTop: 18 }}>
      <div className="relative flex items-end gap-1.5 sm:gap-3" style={{ height }}>
        <i aria-hidden className="absolute inset-x-0 bottom-0 h-px bg-line" />
        {target ? (
          <div aria-hidden className="pointer-events-none absolute inset-x-0 z-10 border-t-2 border-ink/70" style={{ bottom: `${(target / top) * (height - 22)}px` }}>
            <span className="absolute -top-[18px] right-0 rounded bg-card px-1 text-[10.5px] font-semibold text-muted">{targetLabel ?? `Target ${format(target)}`}</span>
          </div>
        ) : null}
        {items.map((i) => {
          const label = `${i.label}${i.sub ? ` ${i.sub}` : ''}: ${format(i.value)}${i.flag ? ', below target' : ''}`
          return (
            <Tooltip key={i.key} content={<><b>{i.label}{i.sub ? ` ${i.sub}` : ''}</b><br />{format(i.value)}{target ? <><br />Target {format(target)}</> : null}{i.flag && <><br />Below target</>}</>}>
              <button type="button" aria-label={label} onClick={() => onOpen?.(i.key)} disabled={!onOpen} className="group relative flex h-full flex-1 flex-col items-center justify-end rounded-lg transition hover:bg-line2/70 focus-visible:bg-line2/70 group-hover/cols:opacity-35 group-focus-within/cols:opacity-35 hover:!opacity-100 focus-visible:!opacity-100">
                {valueLabels && i.value > 0 && <span className="num mb-1 text-[10.5px] font-semibold text-muted">{format(i.value)}</span>}
                <i className={clsx('block w-full max-w-6 rounded-t-[4px] transition group-hover:brightness-110', i.muted && 'opacity-40')} style={{ height: `${Math.max(i.value > 0 ? 2 : 0, (i.value / top) * (height - 22))}px`, background: i.color }} />
              </button>
            </Tooltip>
          )
        })}
      </div>
      <div className="mt-1.5 flex gap-1.5 sm:gap-3">
        {items.map((i) => (
          <div key={i.key} className="flex-1 text-center">
            <div className={clsx('text-[11px] font-semibold', i.flag ? 'text-bad' : 'text-muted')}>{i.label}{i.flag && <span aria-hidden className="ml-0.5">•</span>}</div>
            {i.sub && <div className="num text-[10.5px] text-faint">{i.sub}</div>}
          </div>
        ))}
      </div>
    </div>
  )
}

export interface LinePoint { x: string; label: string; value: number | null; target?: number | null }

/** A 2px line with >=8px markers ringed in the surface colour, a crosshair that snaps to the nearest X, and the same readout on keyboard focus. */
export function LineChart({ points, format, yMax, yTicks, height = 190, name, onPick, gap }: { points: LinePoint[]; format: (n: number) => string; yMax?: number; yTicks?: number[]; height?: number; name: string; onPick?: (i: number) => void; gap?: (value: number, target: number) => string }) {
  const [active, setActive] = useState<number | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const [W, setW] = useState(640) // measured, so text and markers keep their real pixel size on a phone and on a wide screen
  useEffect(() => {
    const el = box.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const H = height, L = 44, R = 14, T = 12, B = 26
  const vals = points.flatMap((p) => [p.value, p.target ?? null]).filter((v): v is number => v != null)
  const top = yMax ?? Math.max(1, ...vals) * 1.1
  const ticks = yTicks ?? [0, top / 2, top]
  const px = (i: number) => L + (points.length <= 1 ? (W - L - R) / 2 : (i / (points.length - 1)) * (W - L - R))
  const py = (v: number) => T + (1 - v / top) * (H - T - B)
  const segments = useMemo(() => {
    const out: string[] = []
    let cur = ''
    points.forEach((p, i) => {
      if (p.value == null) { if (cur) out.push(cur); cur = ''; return }
      cur += `${cur ? 'L' : 'M'}${px(i).toFixed(1)},${py(p.value).toFixed(1)}`
    })
    if (cur) out.push(cur)
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, top, height])
  const targets = points.map((p, i) => (p.target != null ? `${px(i).toFixed(1)},${py(p.target).toFixed(1)}` : null)).filter(Boolean)
  const every = Math.max(1, Math.ceil(points.length / Math.max(2, Math.floor((W - L - R) / 64))))
  const a = active != null ? points[active] : null
  return (
    <div ref={box} className="relative" onPointerLeave={() => setActive(null)}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="block" role="img" aria-label={`${name}: ${points.filter((p) => p.value != null).map((p) => `${p.label} ${format(p.value!)}`).join(', ')}`}>
        {ticks.map((t) => (
          <g key={t}><line x1={L} x2={W - R} y1={py(t)} y2={py(t)} stroke="var(--line)" strokeWidth="1" /><text x={L - 8} y={py(t) + 4} textAnchor="end" fontSize="10.5" fill="var(--faint)">{format(t)}</text></g>
        ))}
        {points.map((p, i) => i % every === 0 && <text key={p.x} x={px(i)} y={H - 6} textAnchor="middle" fontSize="10.5" fill="var(--faint)">{p.x}</text>)}
        {targets.length > 1 && <polyline points={targets.join(' ')} fill="none" stroke="var(--faint)" strokeWidth="1.5" strokeDasharray="1 0" opacity=".8" />}
        {active != null && <line x1={px(active)} x2={px(active)} y1={T} y2={H - B} stroke="var(--ghostline)" strokeWidth="1" />}
        {segments.map((d, i) => <path key={i} d={d} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />)}
        {points.map((p, i) => p.value != null && (
          <g key={p.x}>
            <circle cx={px(i)} cy={py(p.value)} r={active === i ? 5.5 : 4} fill="var(--accent)" stroke="var(--card)" strokeWidth="2" />
            <circle cx={px(i)} cy={py(p.value)} r="16" fill="transparent" tabIndex={0} role="img" aria-label={`${p.label}: ${format(p.value)}`} onPointerEnter={() => setActive(i)} onFocus={() => setActive(i)} onBlur={() => setActive(null)} onClick={() => onPick?.(i)} className={clsx('outline-none focus-visible:stroke-accent', onPick && 'cursor-pointer')} />
          </g>
        ))}
      </svg>
      {a && a.value != null && (
        <div role="status" className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-lg bg-[var(--tipbg)] px-3 py-2 text-xs text-[var(--tipink)] shadow-lg" style={{ left: px(active!), top: py(a.value), marginTop: -10 }}>
          <b className="num block text-sm font-semibold">{format(a.value)}</b><span className="opacity-80">{a.label}</span>{a.target != null && <span className="mt-0.5 block opacity-80">Target {format(a.target)}{gap && a.value != null ? ` · ${gap(a.value, a.target)}` : ''}</span>}
        </div>
      )}
    </div>
  )
}

export interface HeatCell { date: string; value: number; label: string }

/** Weeks as columns, Monday to Sunday as rows. One hue, light to dark; cells are the hit targets (one shared tooltip). */
export function Heatmap({ cells, weeks, max, name, onPick }: { cells: (HeatCell | null)[]; weeks: number; max: number; name: string; onPick?: (date: string) => void }) {
  const [hover, setHover] = useState<{ c: HeatCell; x: number; y: number } | null>(null)
  const level = (v: number) => (v <= 0 ? 0 : v / max > 0.75 ? 4 : v / max > 0.5 ? 3 : v / max > 0.25 ? 2 : 1)
  const colors = ['var(--h0)', 'var(--h1)', 'var(--h2)', 'var(--h3)', 'var(--h4)']
  return (
    <div className="max-w-[760px]">
      <div className="flex gap-2">
        <div className="grid flex-none grid-rows-7 gap-[3px] text-[10px] font-medium text-faint" aria-hidden>
          {['Mon', '', 'Wed', '', 'Fri', '', ''].map((l, i) => <span key={i} className="flex items-center leading-none">{l}</span>)}
        </div>
        <div className="relative min-w-0 flex-1" onPointerLeave={() => setHover(null)}>
          <div className="grid gap-[3px]" role="img" aria-label={name} style={{ gridTemplateColumns: `repeat(${weeks}, minmax(0, 1fr))`, gridTemplateRows: 'repeat(7, auto)', gridAutoFlow: 'column' }}>
            {cells.map((c, i) => c ? (
              <i key={c.date} onPointerEnter={(e) => setHover({ c, x: e.currentTarget.offsetLeft + e.currentTarget.offsetWidth / 2, y: e.currentTarget.offsetTop })}
                onClick={() => onPick?.(c.date)} className={clsx('block aspect-square rounded-[3px] transition hover:ring-2 hover:ring-ink', onPick && 'cursor-pointer')} style={{ background: colors[level(c.value)] }} />
            ) : <i key={`e${i}`} className="block aspect-square" />)}
          </div>
          {hover && <div className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-lg bg-[var(--tipbg)] px-2.5 py-1.5 text-xs text-[var(--tipink)] shadow-lg" style={{ left: hover.x, top: hover.y - 6 }}><b className="num">{hover.c.label}</b><br /><span className="opacity-80">{hover.c.date}</span>{onPick && <><br /><span className="opacity-70">Click to open that day</span></>}</div>}
        </div>
      </div>
      <div className="mt-2.5 flex items-center justify-end gap-1.5 text-[10.5px] text-faint" aria-hidden>Less{colors.map((c) => <i key={c} className="size-3 rounded-[3px]" style={{ background: c }} />)}More</div>
    </div>
  )
}

export interface TreeTile { key: string; label: string; path?: string; value: number; color: string; share: number; to?: string }

/** Where the time went: area is minutes. Tiles keep a 2px surface gap; a label only appears where it fits. */
export function Treemap({ tiles, onOpen, aspect = 2.4 }: { tiles: TreeTile[]; onOpen?: (t: TreeTile) => void; aspect?: number }) {
  const rects = useMemo(() => squarify(tiles.map((t) => ({ key: t.key, value: t.value })), aspect), [tiles, aspect])
  const byKey = new Map(tiles.map((t) => [t.key, t]))
  return (
    <div className="relative w-full" style={{ aspectRatio: String(aspect) }} role="group" aria-label="Time by category">
      {rects.map((r) => {
        const t = byKey.get(r.key)!
        const roomy = r.w > 0.16 && r.h > 0.26, mid = r.w > 0.09 && r.h > 0.16
        return (
          <Tooltip key={r.key} content={<><b>{t.path ?? t.label}</b><br />Hours {hm(t.value)}<br />Share of waking time {Math.round(t.share * 100)}%</>}>
            <button type="button" aria-label={`${t.label}: ${hm(t.value)}`} onClick={() => onOpen?.(t)} disabled={!onOpen}
              className="group absolute p-[1px] text-left" style={{ left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.w * 100}%`, height: `${r.h * 100}%` }}>
              <span className="flex h-full w-full flex-col justify-between overflow-hidden rounded-md p-1.5 text-white ring-ink transition group-hover:ring-2 group-focus-visible:ring-2" style={{ background: t.color }}>
                {mid && <span className="truncate text-[11.5px] font-semibold leading-tight [text-shadow:0_1px_1px_rgb(0_0_0/.25)]">{t.label}</span>}
                {roomy && <span className="num text-[11px] font-medium opacity-90">{hm(t.value)}</span>}
              </span>
            </button>
          </Tooltip>
        )
      })}
    </div>
  )
}

export interface ClockArc { key: string; title: string; category: string; range: string; minutes: number; startMin: number; endMin: number; color: string }
export interface ClockGap { key: string; range: string; minutes: number; startMin: number; endMin: number }

/** 24 hours as a ring: angle is time of day (midnight at the top). Hover or focus an arc and it widens, the rest fade, and the centre becomes
 *  that entry, so no tooltip covers the ring (Hover & Tooltip Spec, pattern 7). Click scrolls the log to it. */
export function DayClock({ arcs, gaps, centre, sub, active, onActive, onPick, size = 250 }: {
  arcs: ClockArc[]; gaps: ClockGap[]; centre: string; sub: string; active?: string | null; onActive?: (key: string | null) => void; onPick?: (key: string) => void; size?: number
}) {
  const SW = 22, WIDE = 30, c = size / 2, R = c - WIDE / 2 - 26 // leave room outside the ring for the hour labels
  const pt = (min: number, r = R) => { const a = (min / 1440) * 2 * Math.PI - Math.PI / 2; return [c + r * Math.cos(a), c + r * Math.sin(a)] as const }
  const arc = (s0: number, e: number) => {
    const [x1, y1] = pt(s0), [x2, y2] = pt(Math.max(s0 + 0.5, e))
    return `M${x1.toFixed(2)},${y1.toFixed(2)} A${R},${R} 0 ${e - s0 > 720 ? 1 : 0} 1 ${x2.toFixed(2)},${y2.toFixed(2)}`
  }
  const hot = arcs.find((a) => a.key === active), hotGap = gaps.find((g) => g.key === active)
  const dim = active ? 0.3 : 1
  const hit = (key: string, label: string, d: string, extra: string) => (
    <path key={`h${key}`} d={d} fill="none" stroke="transparent" strokeWidth={WIDE + 14} tabIndex={0} role="button" aria-label={label} className={clsx('cursor-pointer outline-none', extra)}
      onPointerEnter={() => onActive?.(key)} onPointerLeave={() => onActive?.(null)} onFocus={() => onActive?.(key)} onBlur={() => onActive?.(null)} onClick={() => onPick?.(key)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPick?.(key) } }} />
  )
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="mx-auto block w-full max-w-[280px]" role="group" aria-label={`24 hours: ${centre} logged ${sub}`}>
      <defs><pattern id="clock-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="var(--line2)" /><rect width="2.5" height="6" fill="color-mix(in srgb, var(--bad) 40%, transparent)" /></pattern></defs>
      <circle cx={c} cy={c} r={R} fill="none" stroke="var(--line2)" strokeWidth={SW} />
      {gaps.map((g) => <path key={g.key} d={arc(g.startMin, g.endMin)} fill="none" stroke="url(#clock-hatch)" strokeWidth={active === g.key ? WIDE : SW} opacity={active && active !== g.key ? dim : 1} className="transition-all duration-150" />)}
      {arcs.map((a) => <path key={a.key} d={arc(a.startMin + 0.4, a.endMin - 0.4)} fill="none" stroke={a.color} strokeWidth={active === a.key ? WIDE : SW} opacity={active && active !== a.key ? dim : 1} className="transition-all duration-150" />)}
      {[0, 6, 12, 18].map((h) => { const [x, y] = pt(h * 60, R + WIDE / 2 + 12); return <text key={h} x={x} y={y + 3.5} textAnchor="middle" fontSize="10" fill="var(--faint)">{h === 0 ? '12a' : h === 12 ? '12p' : h > 12 ? `${h - 12}p` : `${h}a`}</text> })}
      {arcs.map((a) => hit(a.key, `${a.title}, ${a.range}, ${hm(a.minutes)}`, arc(a.startMin, a.endMin), 'focus-visible:[stroke:var(--accent)] focus-visible:[stroke-opacity:.25]'))}
      {gaps.map((g) => hit(g.key, `Not logged, ${g.range}, ${hm(g.minutes)}`, arc(g.startMin, g.endMin), 'focus-visible:[stroke:var(--bad)] focus-visible:[stroke-opacity:.2]'))}
      <g aria-live="polite" pointerEvents="none">
        {hot ? <>
          <text x={c} y={c - 20} textAnchor="middle" fontSize="11" fontWeight="600" fill="var(--muted)">{hot.category}</text>
          <text x={c} y={c + 6} textAnchor="middle" fontSize="26" fontWeight="600" className="num" fill="var(--ink)">{hm(hot.minutes)}</text>
          <foreignObject x={c - 62} y={c + 14} width="124" height="40"><div className="line-clamp-2 text-center text-[10.5px] leading-tight text-muted">{hot.title} · {hot.range}</div></foreignObject>
        </> : hotGap ? <>
          <text x={c} y={c - 20} textAnchor="middle" fontSize="11" fontWeight="600" fill="var(--bad)">Unlogged</text>
          <text x={c} y={c + 6} textAnchor="middle" fontSize="26" fontWeight="600" className="num" fill="var(--bad)">{hm(hotGap.minutes)}</text>
          <text x={c} y={c + 26} textAnchor="middle" fontSize="10.5" fill="var(--muted)">{hotGap.range}</text>
        </> : <>
          <text x={c} y={c - 2} textAnchor="middle" fontSize="26" fontWeight="600" className="num" fill="var(--ink)">{centre}</text>
          <text x={c} y={c + 18} textAnchor="middle" fontSize="11" fill="var(--muted)">{sub}</text>
        </>}
      </g>
    </svg>
  )
}
