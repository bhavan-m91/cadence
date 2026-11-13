import clsx from 'clsx'
import { edge, tint } from '@/lib/colors'
import { Icon } from '../ui/Icon'

/** Parent category = filled chip (design chip style guide). */
export function CategoryChip({ name, color, className }: { name: string; color: string; className?: string }) {
  return (
    <span className={clsx('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold leading-normal', className)} style={{ background: tint(color, 20), color: 'var(--ink)', boxShadow: `inset 0 0 0 1px ${edge(color, 35)}` }}>
      <i className="size-[7px] flex-none rounded-[2px]" style={{ background: color }} />
      {name}
    </span>
  )
}

interface TagChipProps {
  name: string
  color: string
  source?: string
  over?: boolean
  needsCheck?: boolean
  onRemove?: () => void
  title?: string
}

/** Tag = outlined chip with a colour dot. Sparkle = auto-tagged; dashed amber = needs a check; red ring = over its cap. */
export function TagChip({ name, color, source, over, needsCheck, onRemove, title }: TagChipProps) {
  return (
    <span
      title={title}
      className={clsx(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border bg-card py-0.5 pl-[7px] text-[11px] font-semibold leading-normal text-ink',
        onRemove ? 'pr-1' : 'pr-2',
        needsCheck ? 'border-dashed border-warn' : over ? 'border-bad ring-2 ring-bad/25' : 'border-line',
      )}
    >
      <i className="size-[7px] flex-none rounded-[2px]" style={{ background: color }} />
      #{name}
      {source && source !== 'user' && <Icon name="sparkle" size={11} className="text-faint" />}
      {needsCheck && <span aria-label="Needs a check" className="text-warn">?</span>}
      {onRemove && (
        <button type="button" aria-label={`Remove tag ${name}`} onClick={onRemove} className="flex size-4 items-center justify-center rounded-full text-faint hover:bg-line2 hover:text-ink">
          <Icon name="x" size={11} />
        </button>
      )}
    </span>
  )
}
