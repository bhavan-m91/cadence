import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { DayTimeline } from '@/api/types'
import { CoverageStrip24h } from './domain/CoverageStrip24h'
import { TagChip } from './domain/Chips'
import { isoToRange, rangeMinutes, rangeToIso } from './domain/TimeRangeInput'
import { ErrorState } from './ui/Feedback'
import { ApiError } from '@/api/client'

describe('TagChip', () => {
  it('shows the # name, flags needs-check and offers an accessible remove button', async () => {
    const onRemove = vi.fn()
    render(<TagChip name="p0" color="#3E86D4" needsCheck onRemove={onRemove} />)
    expect(screen.getByText('#p0')).toBeInTheDocument()
    expect(screen.getByLabelText('Needs a check')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Remove tag p0' }))
    expect(onRemove).toHaveBeenCalled()
  })
})

describe('ErrorState', () => {
  it('explains the error, shows the request id and offers Retry', async () => {
    const retry = vi.fn()
    render(<ErrorState error={new ApiError(500, 'INTERNAL', 'Something went wrong', {}, 'req-42')} onRetry={retry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong')
    expect(screen.getByText('Request id req-42')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(retry).toHaveBeenCalled()
  })
})

describe('TimeRangeInput helpers', () => {
  const tz = 'Asia/Kolkata'
  it('treats an end at or before the start as the next day (sleep)', () => {
    const v = { date: '2025-06-02', start: '23:00', end: '07:00' }
    expect(rangeMinutes(v, tz)).toBe(480)
    expect(rangeToIso(v, tz).end_at).toBe('2025-06-03T01:30:00.000Z')
    expect(rangeMinutes({ date: '2025-06-02', start: '09:00', end: '10:30' }, tz)).toBe(90)
  })
  it('round-trips an existing activity into form values', () => {
    expect(isoToRange('2025-06-02T04:00:00Z', '2025-06-02T05:30:00Z', tz)).toEqual({ date: '2025-06-02', start: '09:30', end: '11:00' })
  })
})

describe('CoverageStrip24h', () => {
  const day = {
    date: '2025-06-02', day_start_at: '2025-06-01T18:30:00Z', day_end_at: '2025-06-02T18:30:00Z', unplaced: [], planned: [],
    coverage: { placed: 540, logged: 540, elapsed: 1440, unlogged: 900, pct: 0.375, complete: false },
    blocks: [{ id: 'a', title: 'Work', start_at: '2025-06-02T03:30:00Z', end_at: '2025-06-02T12:30:00Z', minutes: 540, category: { id: 'c', name: 'Deep work', path_names: 'Work › Deep work', color: '#3E86D4' } }],
    gaps: [{ start_at: '2025-06-01T18:30:00Z', end_at: '2025-06-02T03:30:00Z', minutes: 540 }],
  } as unknown as DayTimeline
  it('describes the day for assistive tech and makes gaps clickable', async () => {
    const onGap = vi.fn()
    render(<CoverageStrip24h day={day} tz="Asia/Kolkata" onGap={onGap} />)
    expect(screen.getByRole('img', { name: /Logged 9h of 24h, 1 gaps/ })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Unlogged 9h/ }))
    expect(onGap).toHaveBeenCalledWith(day.gaps[0])
  })
})
