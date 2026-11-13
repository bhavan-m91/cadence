import type { components } from './generated/schema'

type S = components['schemas']

export type User = S['UserOut']
export type Preferences = S['PreferencesOut']
export type Activity = S['ActivityOut']
export type ActivityDetail = S['ActivityDetail']
export type ActivityTagOut = S['ActivityTagOut']
export type ActivityEvent = S['EventOut']
export type CategoryNode = S['CategoryNode']
export type Category = S['CategoryOut']
export type CategoryChip = S['CategoryChip']
export type Tag = S['TagOut']
export type KeywordRule = S['KeywordRuleOut']
export type Task = S['TaskOut']
export type Project = S['ProjectOut']
export type Timeline = S['TimelineOut']
export type DayTimeline = S['DayTimeline']
export type Block = S['Block']
export type Gap = S['Gap']
export type UnplacedItem = S['UnplacedItem']
export type AuthEvent = S['AuthEventOut']
export type ExportJob = S['ExportOut']

export type ActivityCreate = S['ActivityCreate']
export type ActivityPatch = S['ActivityPatch']

/** Endpoints without a response model are typed by hand. */
export interface TaskDetail extends Task {
  rollup: { total_minutes: number; by_week: { key: string; minutes: number }[]; by_day: { key: string; minutes: number }[]; first_logged: string | null; last_logged: string | null }
  activities: Activity[]
}

export interface TagDetail extends Tag {
  by_day: { date: string; minutes: number }[]
  recent_activities: Activity[]
  total_minutes: number
  keywords: string[]
}

export interface Meta {
  next_cursor?: string | null
  [k: string]: unknown
}
