import * as Popover from '@radix-ui/react-popover'
import clsx from 'clsx'
import {
  Children, Fragment, forwardRef, isValidElement, useEffect, useId, useMemo, useRef, useState,
  type ChangeEvent, type KeyboardEvent, type ReactElement, type ReactNode, type SelectHTMLAttributes,
} from 'react'
import { Icon } from './Icon'

/** The design system's dropdown. A drop-in for `<select>`: same `value` / `onChange(e.target.value)` and the same `<option>` / `<optgroup>` children,
 *  so every call site keeps working while the menu itself is drawn with our tokens instead of the operating system's. */

interface Opt { value: string; node: ReactNode; text: string; disabled: boolean; group?: string }

const textOf = (n: ReactNode): string => (typeof n === 'string' || typeof n === 'number' ? String(n) : Array.isArray(n) ? n.map(textOf).join('') : isValidElement(n) ? textOf((n.props as { children?: ReactNode }).children) : '')

function parse(children: ReactNode, group?: string): Opt[] {
  const out: Opt[] = []
  Children.forEach(children, (c) => {
    if (!isValidElement(c)) return
    const el = c as ReactElement<{ value?: string | number; children?: ReactNode; disabled?: boolean; label?: string }>
    if (el.type === 'option') {
      const node = el.props.children
      out.push({ value: String(el.props.value ?? textOf(node)), node, text: textOf(node), disabled: !!el.props.disabled, group })
    } else if (el.type === 'optgroup') out.push(...parse(el.props.children, el.props.label))
    else if (el.type === Fragment) out.push(...parse(el.props.children, group))
  })
  return out
}

type Props = Omit<SelectHTMLAttributes<HTMLSelectElement>, 'onChange' | 'value' | 'children'> & {
  value?: string | number
  onChange?: (e: ChangeEvent<HTMLSelectElement>) => void
  dense?: boolean
  children?: ReactNode
}

export const Select = forwardRef<HTMLButtonElement, Props>(function Select(
  { value = '', onChange, dense, children, className, id, disabled, name, 'aria-label': ariaLabel, 'aria-describedby': describedBy, 'aria-invalid': invalid },
  ref,
) {
  const opts = useMemo(() => parse(children), [children])
  const current = opts.find((o) => o.value === String(value))
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const list = useRef<HTMLDivElement>(null)
  const typed = useRef({ s: '', t: 0 })
  const lid = useId()

  const enabled = opts.map((o, i) => (o.disabled ? -1 : i)).filter((i) => i >= 0)
  const move = (dir: 1 | -1 | 'first' | 'last') => {
    if (!enabled.length) return
    if (dir === 'first') return setActive(enabled[0])
    if (dir === 'last') return setActive(enabled[enabled.length - 1])
    const at = enabled.indexOf(active)
    setActive(enabled[(at + dir + enabled.length) % enabled.length] ?? enabled[0])
  }
  const choose = (o: Opt) => {
    if (o.disabled) return
    onChange?.({ target: { value: o.value, name }, currentTarget: { value: o.value, name } } as unknown as ChangeEvent<HTMLSelectElement>)
    setOpen(false)
  }

  useEffect(() => {
    if (!open) return
    const at = opts.findIndex((o) => o.value === String(value))
    setActive(at >= 0 ? at : (enabled[0] ?? 0))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])
  useEffect(() => { if (open) list.current?.querySelector<HTMLElement>(`[data-i="${active}"]`)?.scrollIntoView?.({ block: 'nearest' }) }, [active, open])

  const onListKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); move(1) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1) }
    else if (e.key === 'Home') { e.preventDefault(); move('first') }
    else if (e.key === 'End') { e.preventDefault(); move('last') }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); const o = opts[active]; if (o) choose(o) }
    else if (e.key === 'Tab') setOpen(false)
    else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey) { // type to jump, like a native menu
      const now = Date.now()
      typed.current = { s: now - typed.current.t > 700 ? e.key.toLowerCase() : typed.current.s + e.key.toLowerCase(), t: now }
      const hit = opts.findIndex((o) => !o.disabled && o.text.toLowerCase().startsWith(typed.current.s))
      if (hit >= 0) setActive(hit)
    }
  }

  let lastGroup: string | undefined
  return (
    <Popover.Root open={open} onOpenChange={(o) => !disabled && setOpen(o)}>
      <Popover.Trigger asChild>
        <button
          ref={ref} id={id} type="button" role="combobox" aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? lid : undefined}
          aria-label={ariaLabel} aria-describedby={describedBy} aria-invalid={invalid} disabled={disabled} name={name}
          onKeyDown={(e) => { if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); setOpen(true) } }}
          className={clsx(
            'flex w-full items-center justify-between gap-2 rounded-[11px] border border-line bg-card px-3.5 text-left text-sm text-ink outline-none transition',
            'hover:border-ghostline focus-visible:border-accent focus-visible:shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_18%,transparent)] disabled:cursor-not-allowed disabled:opacity-60',
            open && 'border-accent shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_18%,transparent)]', invalid && 'border-bad', dense ? 'h-9' : 'h-11', className,
          )}
        >
          <span className={clsx('min-w-0 flex-1 truncate', !current && 'text-faint')}>{current ? current.node : ' '}</span>
          <Icon name="chevronDown" size={15} className={clsx('flex-none text-faint transition-transform', open && 'rotate-180')} />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom" align="start" sideOffset={6} collisionPadding={12}
          onOpenAutoFocus={(e) => { e.preventDefault(); list.current?.focus() }}
          className="z-[80] min-w-[var(--radix-popover-trigger-width)] max-w-[min(360px,calc(100vw-24px))] overflow-hidden rounded-xl border border-line bg-card p-1 shadow-xl data-[state=open]:animate-[tip_.12s_ease-out]"
        >
          <div
            ref={list} id={lid} role="listbox" tabIndex={-1} aria-label={ariaLabel} aria-activedescendant={`${lid}-${active}`} onKeyDown={onListKey}
            className="max-h-[min(320px,var(--radix-popover-content-available-height,320px))] overflow-y-auto outline-none"
          >
            {opts.length === 0 && <div className="px-3 py-2 text-[13px] text-faint">Nothing to choose</div>}
            {opts.map((o, i) => {
              const header = o.group && o.group !== lastGroup ? o.group : null
              lastGroup = o.group
              const selected = o.value === String(value)
              return (
                <Fragment key={`${o.value}-${i}`}>
                  {header && <div role="presentation" className="px-3 pb-1 pt-2 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-faint">{header}</div>}
                  <div
                    id={`${lid}-${i}`} data-i={i} role="option" aria-selected={selected} aria-disabled={o.disabled || undefined}
                    onPointerMove={() => !o.disabled && setActive(i)} onClick={() => choose(o)}
                    className={clsx('flex min-h-9 cursor-pointer items-center gap-2 rounded-lg px-3 py-1.5 text-[13px]', o.group && 'pl-4',
                      active === i && !o.disabled && 'bg-line2', selected ? 'font-semibold text-ink' : 'text-ink', o.disabled && 'cursor-not-allowed opacity-45')}
                  >
                    <span className="min-w-0 flex-1 truncate">{o.node}</span>
                    {selected && <Icon name="check" size={15} strokeWidth={2.4} className="flex-none text-accent-ink" />}
                  </div>
                </Fragment>
              )
            })}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
})
