/** Live counters shown with a tilde while typing (FR-025, D-21). Cheap, client-side, and clearly labelled as estimates. */
const VERB = /\b(worked|work|started|woke|slept|had|attended|went|spent|met|called|took|read|watched|scrolled|wasted|cooked|ate|drove|walked|ran|debugged|fixed|wrote|reviewed|researched|brainstormed|played|studied|cleaned|left|joined|finished|did|gym|lunch|dinner|breakfast|meeting)\b/i
const TIME = /\b\d{1,2}(:\d{2})?\s*(am|pm)\b|\b(from|until|till|at)\s+\d{1,2}\b|\b\d+\s*(hours?|hrs?|minutes?|mins?)\b|\bhalf an hour\b|\ban hour\b/i

export const wordCount = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0)

export function approxActivities(t: string): number {
  const parts = t.split(/(?<=[.!?])\s+|\s+(?=(?:and then|then|after that)\b)/i).filter((s) => s.trim().length > 3)
  return parts.filter((s) => VERB.test(s) || TIME.test(s)).length
}

export function phraseIn(text: string, phrase: string): boolean {
  const p = phrase.trim()
  if (!p) return false
  const esc = p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`(?<![\\p{L}\\p{N}_])${esc}(?![\\p{L}\\p{N}_])`, 'iu').test(text)
}
