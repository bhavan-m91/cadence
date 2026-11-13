import * as RT from '@radix-ui/react-tooltip'
import type { ReactNode } from 'react'

/** One tooltip look everywhere (dark in both themes). Also opens on keyboard focus, as the hover spec requires. */
export function Tooltip({ content, children, side = 'top' }: { content: ReactNode; children: ReactNode; side?: 'top' | 'bottom' | 'left' | 'right' }) {
  return (
    <RT.Provider delayDuration={0} skipDelayDuration={0}>
      <RT.Root>
        <RT.Trigger asChild>{children}</RT.Trigger>
        <RT.Portal>
          <RT.Content side={side} sideOffset={6} collisionPadding={8} className="z-[90] max-w-[260px] animate-[tip_.12s_ease-out] rounded-lg bg-[var(--tipbg)] px-3 py-2 text-xs text-[var(--tipink)] shadow-lg">
            {content}
            <RT.Arrow className="fill-[var(--tipbg)]" />
          </RT.Content>
        </RT.Portal>
      </RT.Root>
    </RT.Provider>
  )
}
