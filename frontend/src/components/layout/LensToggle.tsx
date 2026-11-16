import clsx from 'clsx'
import { useCategories } from '@/api/hooks/useTaxonomy'
import { useLensStore, type Lens } from '@/stores/lensStore'

/** All / Work / Personal. A demo-friendly switch: pick a side and every chart, total and calendar block on the page follows it. */
export function LensToggle({ className }: { className?: string }) {
  const { lens, setLens } = useLensStore()
  const { data: tree } = useCategories()
  const color = (k: string) => tree?.find((r) => r.root_kind === k)?.color
  const opts: { value: Lens; label: string; dot?: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'work', label: 'Work', dot: color('work') ?? 'var(--sky)' },
    { value: 'personal', label: 'Personal', dot: color('personal') ?? 'var(--teal)' },
  ]
  return (
    <div role="radiogroup" aria-label="Show work, personal or everything" className={clsx('flex rounded-[10px] border border-line bg-line2 p-[3px]', className)}>
      {opts.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={lens === o.value} onClick={() => setLens(o.value)}
          className={clsx('flex min-h-[30px] items-center gap-1.5 rounded-[7px] px-3 text-[12.5px]', lens === o.value ? 'bg-card font-semibold text-ink shadow-sm' : 'font-medium text-muted hover:text-ink')}>
          {o.dot && <i className="size-2 rounded-[3px]" style={{ background: o.dot }} aria-hidden />}{o.label}
        </button>
      ))}
    </div>
  )
}

/** A line under the header when a lens is on, so nobody mistakes a filtered view for the whole day. */
export function LensNotice() {
  const { lens, setLens } = useLensStore()
  if (lens === 'all') return null
  return (
    <div role="status" className="flex flex-wrap items-center gap-2 border-b border-line bg-tint px-4 py-2 text-[12.5px] md:px-7">
      <span>Showing <b className="font-semibold">{lens === 'work' ? 'work' : 'personal life'} only</b>{lens === 'personal' ? ' (sleep included)' : ''}. Coverage still counts the whole day.</span>
      <button type="button" className="font-semibold text-accent-ink hover:underline" onClick={() => setLens('all')}>Show everything</button>
    </div>
  )
}
