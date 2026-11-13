import * as RD from '@radix-ui/react-dialog'
import clsx from 'clsx'
import type { ReactNode } from 'react'
import { Icon } from './Icon'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}

export function Dialog({ open, onOpenChange, title, description, children, footer, wide }: Props) {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        <RD.Overlay className="fixed inset-0 z-40 bg-black/40 data-[state=open]:animate-[fade_.12s_ease-out]" />
        <RD.Content
          className={clsx('fixed left-1/2 top-1/2 z-50 flex max-h-[90vh] w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-line bg-card shadow-2xl', wide ? 'max-w-2xl' : 'max-w-md')}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div>
              <RD.Title className="text-base font-semibold">{title}</RD.Title>
              <RD.Description className={clsx('mt-0.5 text-[13px] text-muted', !description && 'sr-only')}>{description ?? title}</RD.Description>
            </div>
            <RD.Close aria-label="Close" className="flex size-8 items-center justify-center rounded-lg text-muted hover:bg-line2 hover:text-ink">
              <Icon name="x" size={16} />
            </RD.Close>
          </div>
          <div className="overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  )
}
