import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ReviewDraft } from '@/api/types'
import { DraftCard, flagText, initialEdit, type DraftView } from './DraftParts'

const draft = {
  id: 'd1', temp_id: 'a1', order: 0, title: 'Standup', description: null, placement: 'placed',
  start_at: '2026-11-13T04:30:00Z', end_at: '2026-11-13T05:00:00Z', window_start_at: null, window_end_at: null, duration_minutes: 30, time_certainty: 'exact',
  category: { id: 'c1', name: 'Meetings', path_names: 'Work › Meetings', color: '#1c9c8d', root_kind: 'work' },
  tags: [{ tag_id: 't1', name: 'meetings', color: '#555', source: 'rule', confidence: 0.9, reason: null, applied: true, new: false }],
  task: { task_id: null, task_title: null, new_task_title: null, confidence: 0 }, location_type: null, confidence: 0.9, band: 'high', flags: [],
  source: { quote: 'standup', start: 0, end: 7 }, include: true, duplicate_of: null, ideal_row_id: null,
} as unknown as ReviewDraft

const view: DraftView = { title: 'Standup', description: '', category: { name: 'Meetings', color: '#1c9c8d' }, tags: [{ key: 't1', name: 'meetings', color: '#555', source: 'rule', isNew: false, needsCheck: false, removable: true }], minutes: 30, taskLabel: null }

describe('review drafts', () => {
  it('turns flag codes into plain language, with a safe fallback', () => {
    expect(flagText('unplaced')).toMatch(/some time/)
    expect(flagText('brand_new_flag')).toBe('Brand new flag.')
  })

  it('starts the edit state from the draft (times in the user timezone)', () => {
    const e = initialEdit(draft, 'Asia/Kolkata')
    expect(e.range).toEqual({ date: '2026-11-13', start: '10:00', end: '10:30' })
    expect(e.tag_ids).toEqual(['t1'])
  })

  it('lets the person untick, edit and remove a tag from a card', async () => {
    const onInclude = vi.fn(), onEdit = vi.fn(), onRemoveTag = vi.fn()
    render(<DraftCard d={draft} idx={0} view={view} included hot={false} blockers={[]} conflicts={[]} tz="Asia/Kolkata" fmt="12h" onInclude={onInclude} onHover={() => {}} onEdit={onEdit} onRemoveTag={onRemoveTag} onResolve={() => {}} />)
    expect(screen.getByText('10am – 10:30am')).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText('Include Standup'))
    expect(onInclude).toHaveBeenCalledWith(false)
    await userEvent.click(screen.getByRole('button', { name: 'Remove tag meetings' }))
    expect(onRemoveTag).toHaveBeenCalledWith('t1')
    await userEvent.click(screen.getByRole('button', { name: 'Edit Standup' }))
    expect(onEdit).toHaveBeenCalled()
  })

  it('only offers overlap fixes that can work', () => {
    const middle = { draft_id: 'd1', other_id: 'x', other_title: 'Existing', other_is_draft: false, start_at: '2026-11-13T04:40:00Z', end_at: '2026-11-13T04:50:00Z', overlap_minutes: 10 }
    render(<DraftCard d={draft} idx={0} view={view} included hot={false} blockers={[]} conflicts={[middle]} tz="UTC" fmt="12h" onInclude={() => {}} onHover={() => {}} onEdit={() => {}} onRemoveTag={() => {}} onResolve={() => {}} />)
    expect(screen.queryByRole('button', { name: 'Shorten this one' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Replace the other' })).toBeInTheDocument()
  })
})
