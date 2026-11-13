import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../client'
import type { Breakdown, Overview, TrendMetric, Trends } from '../types'

/** Charts keep their previous render while a new range loads (no skeleton flash); the server answers 304 when nothing changed. */
export const useOverview = (scope: 'day' | 'week', anchor: string) =>
  useQuery({ queryKey: ['analytics', 'overview', scope, anchor], queryFn: () => api.get<Overview>('/analytics/overview', { scope, anchor }), placeholderData: keepPreviousData })

export const useBreakdown = (from: string, to: string, by: 'category' | 'tag' | 'task' | 'project' = 'category') =>
  useQuery({ queryKey: ['analytics', 'breakdown', from, to, by], queryFn: () => api.get<Breakdown>('/analytics/breakdown', { from, to, by }), placeholderData: keepPreviousData })

export const useTrends = (metric: TrendMetric, granularity: 'day' | 'week', periods: number) =>
  useQuery({ queryKey: ['analytics', 'trends', metric, granularity, periods], queryFn: () => api.get<Trends>('/analytics/trends', { metric, granularity, periods }), placeholderData: keepPreviousData })
