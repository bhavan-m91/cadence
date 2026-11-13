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

// ---- Phase 2 / 3
export type IdealOverview = components['schemas']['IdealOverviewOut']
export type IdealTemplate = components['schemas']['IdealTemplateOut']
export type IdealAllocation = components['schemas']['AllocationOut']
export type IdealProgress = components['schemas']['ProgressOut']
export type IdealProgressRow = components['schemas']['ProgressRow']
export type EntryOut = components['schemas']['EntryOut']
export type EntrySummary = components['schemas']['EntrySummary']
export type EntryDetail = components['schemas']['EntryDetail']
export type EntryRevision = components['schemas']['RevisionOut']
export type JournalStats = components['schemas']['StatsOut']
export type AiStatus = components['schemas']['AiStatusOut']
export type JobOut = components['schemas']['JobOut']
export type Review = components['schemas']['ReviewOut']
export type ReviewDraft = components['schemas']['ReviewDraft']
export type ReviewTag = components['schemas']['ReviewTag']
export type ReviewGap = components['schemas']['ReviewGap']
export type ReviewConflict = components['schemas']['ReviewConflict']
export type ReviewQuestion = components['schemas']['Question']
export type CommitBody = components['schemas']['CommitIn']
export type CommitResult = components['schemas']['CommitOut']

// ---- Phase 4 analytics (the overview's `charts` bag is an open object in the schema, so it is typed here)
type SS = components['schemas']
export type IdealCompare = SS['IdealCompare']
export type IdealCompareRow = SS['IdealCompareRow']
export type SleepBlock = SS['SleepBlock']
export type FocusBlock = SS['FocusBlock']
export type DayColumn = SS['DayColumn']
export type CategoryTotal = SS['CategoryTotal']
export type TagTotal = SS['TagTotal']
export type TaskTotal = SS['TaskTotal']
export type WorkPersonal = SS['WorkPersonal']
export type Banner = SS['BannerOut']
export type Deadline = SS['DeadlineOut']
export type BreakdownItem = SS['BreakdownItem']
export type Breakdown = SS['BreakdownOut']
export type TrendPoint = SS['TrendPoint']
export type Trends = SS['TrendsOut']
export type TrendMetric = 'adherence' | 'coverage' | 'sleep' | 'focus'
export interface OverviewCharts {
  actual_vs_ideal: IdealCompare | null
  work_vs_personal: WorkPersonal
  coverage_by_day: DayColumn[]
  sleep: SleepBlock
  focus: FocusBlock
  categories: CategoryTotal[]
  top_tasks: TaskTotal[]
  tag_goals: TagTotal[]
  certainty: { recorded: number; estimated: number }
}
export type Overview = Omit<SS['OverviewOut'], 'charts'> & { charts: OverviewCharts }
