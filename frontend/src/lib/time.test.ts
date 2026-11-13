import { addDays, daysBetween, formatClock, formatRange, hm, isoToLocal, localToIso, rangeLabel, snap, weekDates, weekStartOf } from './time'

describe('time helpers', () => {
  it('converts local wall-clock time to UTC for the given zone', () => {
    expect(localToIso('2025-06-02', '09:30', 'Asia/Kolkata')).toBe('2025-06-02T04:00:00.000Z')
    expect(localToIso('2025-06-02', '09:30', 'America/New_York')).toBe('2025-06-02T13:30:00.000Z')
  })

  it('is DST-correct: the same wall time is a different UTC offset across a clock change', () => {
    expect(localToIso('2025-03-08', '12:00', 'America/New_York')).toBe('2025-03-08T17:00:00.000Z') // EST
    expect(localToIso('2025-03-09', '12:00', 'America/New_York')).toBe('2025-03-09T16:00:00.000Z') // EDT
  })

  it('round-trips an instant through a zone', () => {
    expect(isoToLocal('2025-06-02T04:00:00Z', 'Asia/Kolkata')).toEqual({ date: '2025-06-02', time: '09:30' })
    expect(isoToLocal('2025-06-02T20:00:00Z', 'Asia/Kolkata')).toEqual({ date: '2025-06-03', time: '01:30' })
  })

  it('formats clocks and ranges in the design style', () => {
    const a = '2025-06-02T04:00:00Z', b = '2025-06-02T07:30:00Z'
    expect(formatClock(a, 'Asia/Kolkata')).toBe('9:30am')
    expect(formatClock('2025-06-02T06:30:00Z', 'Asia/Kolkata')).toBe('12pm')
    expect(formatClock('2025-06-01T18:30:00Z', 'Asia/Kolkata')).toBe('12am')
    expect(formatClock(a, 'Asia/Kolkata', '24h')).toBe('09:30')
    expect(formatRange(a, b, 'Asia/Kolkata')).toBe('9:30am – 1pm')
  })

  it('formats durations', () => {
    expect([0, 45, 60, 150, 1440, -30].map(hm)).toEqual(['0m', '45m', '1h', '2h 30m', '24h', '-30m'])
  })

  it('does calendar arithmetic without timezones', () => {
    expect(addDays('2025-02-27', 2)).toBe('2025-03-01')
    expect(addDays('2025-01-01', -1)).toBe('2024-12-31')
    expect(daysBetween('2025-06-02', '2025-06-09')).toBe(7)
  })

  it('finds the start of the week for either convention', () => {
    expect(weekStartOf('2026-11-13', 1)).toBe('2026-11-09') // Friday -> Monday
    expect(weekStartOf('2026-11-13', 7)).toBe('2026-11-08') // Sunday start
    expect(weekStartOf('2026-11-09', 1)).toBe('2026-11-09')
    expect(weekDates('2026-11-13', 1)).toHaveLength(7)
    expect(weekDates('2026-11-13', 1)[6]).toBe('2026-11-15')
  })

  it('labels ranges and snaps to 5 minutes', () => {
    expect(rangeLabel('2026-11-09', '2026-11-15')).toBe('Nov 9 – 15')
    expect(rangeLabel('2026-10-28', '2026-11-03')).toBe('Oct 28 – Nov 3')
    expect([7, 8, 12, 13, 62].map((m) => snap(m))).toEqual([5, 10, 10, 15, 60])
  })
})
