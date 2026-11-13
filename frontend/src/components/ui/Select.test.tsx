import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Select } from './Select'

function Demo({ onChange = () => {} }: { onChange?: (v: string) => void }) {
  const [v, setV] = useState('b')
  return (
    <Select aria-label="Pick" value={v} onChange={(e) => { setV(e.target.value); onChange(e.target.value) }}>
      <option value="">None</option>
      <option value="a">Alpha</option>
      <option value="b">Beta</option>
      <optgroup label="More"><option value="c">Gamma</option><option value="d" disabled>Delta</option></optgroup>
      {null}
    </Select>
  )
}

describe('Select', () => {
  it('shows the chosen option and opens a styled listbox with groups, instead of the system menu', async () => {
    render(<Demo />)
    const trigger = screen.getByRole('combobox', { name: 'Pick' })
    expect(trigger).toHaveTextContent('Beta')
    await userEvent.click(trigger)
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    expect(screen.getByText('More')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Beta' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('option', { name: 'Delta' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByText('never')).toBeNull()
  })

  it('calls onChange with e.target.value, like a native select, and closes', async () => {
    const onChange = vi.fn()
    render(<Demo onChange={onChange} />)
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(screen.getByRole('option', { name: 'Gamma' }))
    expect(onChange).toHaveBeenCalledWith('c')
    expect(screen.getByRole('combobox')).toHaveTextContent('Gamma')
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('works from the keyboard: arrows move, Enter chooses, disabled options are skipped, typing jumps', async () => {
    const onChange = vi.fn()
    render(<Demo onChange={onChange} />)
    screen.getByRole('combobox').focus()
    await userEvent.keyboard('{ArrowDown}') // opens on Beta
    await userEvent.keyboard('{ArrowDown}') // Gamma
    await userEvent.keyboard('{ArrowDown}') // Delta is disabled, so wraps to None
    await userEvent.keyboard('{Enter}')
    expect(onChange).toHaveBeenLastCalledWith('')
    await userEvent.keyboard('{ArrowDown}')
    await userEvent.keyboard('a')
    await userEvent.keyboard('{Enter}')
    expect(onChange).toHaveBeenLastCalledWith('a')
  })
})
