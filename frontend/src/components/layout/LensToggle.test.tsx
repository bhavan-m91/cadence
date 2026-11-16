import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { inLens, useLensStore } from '@/stores/lensStore'
import { LensNotice, LensToggle } from './LensToggle'

const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>)

describe('Work / Personal lens', () => {
  beforeEach(() => { localStorage.clear(); useLensStore.setState({ lens: 'all' }) })

  it('switches between all, work and personal, remembers the choice and says what is hidden', async () => {
    wrap(<><LensToggle /><LensNotice /></>)
    expect(screen.getByRole('radio', { name: 'All' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.queryByRole('status')).toBeNull()
    await userEvent.click(screen.getByRole('radio', { name: 'Work' }))
    expect(useLensStore.getState().lens).toBe('work')
    expect(localStorage.getItem('cadence-lens')).toBe('work')
    expect(screen.getByRole('status')).toHaveTextContent('Showing work only')
    await userEvent.click(screen.getByRole('button', { name: 'Show everything' }))
    expect(useLensStore.getState().lens).toBe('all')
  })

  it('counts sleep as personal life', () => {
    expect(inLens('personal', 'sleep')).toBe(true)
    expect(inLens('work', 'sleep')).toBe(false)
    expect(inLens('all', 'work')).toBe(true)
  })
})
