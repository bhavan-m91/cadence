import clsx from 'clsx'
import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { Icon, type IconName } from './Icon'

type Variant = 'primary' | 'ghost' | 'danger' | 'subtle'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: 'sm' | 'md' | 'lg'
  icon?: IconName
  loading?: boolean
}

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-white hover:brightness-95 border border-transparent',
  ghost: 'bg-card text-ink border border-line hover:border-ghostline',
  subtle: 'bg-transparent text-muted hover:text-ink hover:bg-line2 border border-transparent',
  danger: 'bg-bad text-white hover:brightness-95 border border-transparent',
}
const SIZES = { sm: 'h-8 px-3 text-[12.5px] rounded-lg', md: 'h-9 px-3.5 text-[13px] rounded-[9px]', lg: 'h-12 px-5 text-sm rounded-[11px]' }

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant = 'ghost', size = 'md', icon, loading, className, children, disabled, type = 'button', ...rest }, ref,
) {
  return (
    <button
      ref={ref} type={type} disabled={disabled || loading} aria-busy={loading || undefined}
      className={clsx('inline-flex items-center justify-center gap-2 font-semibold whitespace-nowrap transition disabled:opacity-50 disabled:cursor-not-allowed', VARIANTS[variant], SIZES[size], className)}
      {...rest}
    >
      {loading ? <span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden /> : icon && <Icon name={icon} size={16} />}
      {children}
    </button>
  )
})

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: IconName
  label: string
  size?: number
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton({ icon, label, size = 17, className, type = 'button', ...rest }, ref) {
  return (
    <button
      ref={ref} type={type} aria-label={label} title={label}
      className={clsx('flex size-9 flex-none items-center justify-center rounded-[9px] border border-line bg-card text-muted hover:border-ghostline hover:text-ink disabled:opacity-50', className)}
      {...rest}
    >
      <Icon name={icon} size={size} />
    </button>
  )
})
