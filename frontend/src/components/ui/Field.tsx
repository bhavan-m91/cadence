import clsx from 'clsx'
import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from 'react'

interface FieldProps {
  label: ReactNode
  hint?: ReactNode
  error?: string
  action?: ReactNode
  className?: string
  children: (id: string, describedBy: string | undefined) => ReactNode
}

/** Label + control + inline error wired with aria so screen readers announce the problem. */
export function Field({ label, hint, error, action, className, children }: FieldProps) {
  const id = useId()
  const msg = error ?? undefined
  const describedBy = msg ? `${id}-err` : hint ? `${id}-hint` : undefined
  return (
    <div className={clsx('flex flex-col gap-1.5', className)}>
      <label htmlFor={id} className="flex items-center justify-between text-xs font-semibold text-muted">
        <span>{label}</span>
        {action}
      </label>
      {children(id, describedBy)}
      {msg ? <p id={`${id}-err`} role="alert" className="text-xs text-bad">{msg}</p> : hint ? <p id={`${id}-hint`} className="text-xs text-faint">{hint}</p> : null}
    </div>
  )
}

const control = 'w-full rounded-[11px] border border-line bg-card text-ink px-3.5 text-sm outline-none transition focus:border-accent focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_18%,transparent)] disabled:opacity-60 placeholder:text-faint'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean; dense?: boolean }>(function Input(
  { className, invalid, dense, ...rest }, ref,
) {
  return <input ref={ref} aria-invalid={invalid || undefined} className={clsx(control, dense ? 'h-9' : 'h-11', invalid && 'border-bad', className)} {...rest} />
})

export { Select } from './Select'

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={clsx(control, 'min-h-[84px] py-2.5 leading-relaxed', className)} {...rest} />
})
