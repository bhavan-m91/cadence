import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ChartTable, Columns, DayClock, Heatmap, LineChart, MeterList, SegmentedBar } from './charts'

describe('charts', () => {
  it('names every column with its value and marks the ones below target without relying on colour', () => {
    render(<Columns items={[{ key: 'a', label: 'Mon', sub: '3', value: 480, color: '#5e6582' }, { key: 'b', label: 'Tue', sub: '4', value: 300, color: '#d4564f', flag: true }]} target={420} />)
    expect(screen.getByRole('button', { name: 'Mon 3: 8h' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tue 4: 5h, below target' })).toBeInTheDocument()
    expect(screen.getByText('Target 7h')).toBeInTheDocument()
  })

  it('describes a meter row with the actual, the target and where you should be by now', () => {
    render(<MeterList items={[{ key: 'deep', label: 'Deep work', color: '#3e86d4', actual: 360, target: 1200, expected: 480, status: 'under' }]} />)
    expect(screen.getByRole('button', { name: 'Deep work: 6h of 20h, expected 8h by now' })).toBeInTheDocument()
    expect(screen.getByText('Behind')).toBeInTheDocument()
  })

  it('splits a whole into labelled parts with shares', () => {
    render(<SegmentedBar parts={[{ key: 'w', label: 'Work', value: 300, color: '#3e86d4' }, { key: 'p', label: 'Personal', value: 100, color: '#1c9c8d' }]} />)
    expect(screen.getByRole('img', { name: 'Work 5h, Personal 1h 40m' })).toBeInTheDocument()
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('draws gaps for missing points and reads a point back on keyboard focus', async () => {
    const { container } = render(<LineChart name="Adherence" format={(n) => `${Math.round(n * 100)}%`} yMax={1}
      points={[{ x: '1 Jun', label: 'Week of 1 Jun', value: 0.5 }, { x: '8 Jun', label: 'Week of 8 Jun', value: null }, { x: '15 Jun', label: 'Week of 15 Jun', value: 0.8 }]} />)
    expect(container.querySelectorAll('path')).toHaveLength(2) // a missing week breaks the line instead of joining across it
    await userEvent.tab()
    expect(screen.getByRole('status')).toHaveTextContent('50%')
    expect(screen.getByRole('img', { name: /Adherence: Week of 1 Jun 50%, Week of 15 Jun 80%/ })).toBeInTheDocument()
  })

  it('shades heat cells in five steps and leaves padding cells empty', () => {
    const cells = [null, { date: '2025-06-02', value: 0, label: '0m' }, { date: '2025-06-03', value: 240, label: '4h' }]
    const { container } = render(<Heatmap cells={cells} weeks={1} max={240} name="Focus" />)
    const filled = Array.from(container.querySelectorAll('i[style]')).map((e) => (e as HTMLElement).style.background)
    expect(filled[0]).toContain('--h0')
    expect(filled[1]).toContain('--h4')
  })

  it('offers every chart as a table', () => {
    render(<ChartTable caption="Sleep by night" head={['Night', 'Slept']} rows={[['3 Jun', '8h']]} />)
    expect(screen.getByText('View as table')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Sleep by night', hidden: true })).toBeInTheDocument()
  })

  it('turns the 24h ring into the hovered entry: the centre swaps, and the same happens on keyboard focus', async () => {
    let active: string | null = null
    const arcs = [{ key: 'a', title: 'Acme agent architecture', category: 'Deep work', range: '9am – 12pm', minutes: 180, startMin: 540, endMin: 720, color: '#3e86d4' }]
    const gaps = [{ key: 'g', range: '12pm – 1pm', minutes: 60, startMin: 720, endMin: 780 }]
    const { rerender } = render(<DayClock arcs={arcs} gaps={gaps} centre="3h" sub="of 24h" active={active} onActive={(k) => { active = k }} />)
    expect(screen.getByText('of 24h')).toBeInTheDocument()
    await userEvent.tab()
    expect(active).toBe('a')
    rerender(<DayClock arcs={arcs} gaps={gaps} centre="3h" sub="of 24h" active="a" />)
    expect(screen.getByText('Deep work')).toBeInTheDocument()
    expect(screen.getByText(/Acme agent architecture · 9am – 12pm/)).toBeInTheDocument()
    rerender(<DayClock arcs={arcs} gaps={gaps} centre="3h" sub="of 24h" active="g" />)
    expect(screen.getByText('Unlogged')).toBeInTheDocument()
    expect(screen.getByText('12pm – 1pm')).toBeInTheDocument()
  })
})
