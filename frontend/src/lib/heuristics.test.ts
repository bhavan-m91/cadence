import { describe, expect, it } from 'vitest'
import { approxActivities, phraseIn, wordCount } from './heuristics'

describe('heuristics', () => {
  it('counts words', () => {
    expect(wordCount('')).toBe(0)
    expect(wordCount('  one  two\nthree ')).toBe(3)
  })

  it('estimates activities from verbs and times, not filler', () => {
    expect(approxActivities('Worked on the proposal from 9 to 11. Then standup until 11:30. Lunch for half an hour.')).toBe(3)
    expect(approxActivities('hmm. ok. so.')).toBe(0)
  })

  it('matches keyword phrases as whole words only', () => {
    expect(phraseIn('I was debugging the login', 'debugging')).toBe(true)
    expect(phraseIn('I was debuggingly slow', 'debugging')).toBe(false)
    expect(phraseIn('Standup at 10', 'standup')).toBe(true)
    expect(phraseIn('anything', '   ')).toBe(false)
    expect(phraseIn('cost is $5.00 (net)', '$5.00 (net)')).toBe(true)
  })
})
