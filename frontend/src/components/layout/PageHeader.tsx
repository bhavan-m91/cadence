import type { ReactNode } from 'react'
import { IconButton } from '../ui/Button'
import { ThemeToggle } from './ThemeToggle'

export function PageHeader({ title, subtitle, back, children }: { title: string; subtitle?: ReactNode; back?: () => void; children?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-center gap-x-3 gap-y-2.5 border-b border-line bg-card px-4 py-3.5 md:px-7 md:py-4">
      {back && <IconButton icon="arrowLeft" label="Back" onClick={back} className="max-md:order-1" />}
      <div className="mr-auto min-w-0 max-md:order-1 max-md:flex-1">
        <h1 className="m-0 text-xl font-bold tracking-tighter2">{title}</h1>
        {subtitle && <div className="text-[12.5px] text-muted">{subtitle}</div>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2 max-md:order-3 max-md:w-full">{children}</div>}
      <span className="max-md:order-2"><ThemeToggle /></span>
    </header>
  )
}

export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex rounded-[10px] border border-line bg-line2 p-[3px]">
      {options.map((o) => (
        <button
          key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className={`min-h-[30px] rounded-[7px] px-3.5 text-[12.5px] ${value === o.value ? 'bg-card font-semibold text-ink shadow-sm' : 'font-medium text-muted hover:text-ink'}`}
        >{o.label}</button>
      ))}
    </div>
  )
}
