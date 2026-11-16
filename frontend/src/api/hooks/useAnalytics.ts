import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../client'
import type { Breakdown, Overview, TrendMetric, Trends } from '../types'
import { useLensStore } from '@/stores/lensStore'

/** Charts keep their previous render while a new range loads (no skeleton flash); the server answers 304 when nothing changed. */
// Every analytics read follows the Work / Personal lens.
export function useOverview(scope: 'day' | 'week', anchor: string) {
  const lens = useLensStore((s) => s.lens)
  return useQuery({ queryKey: ['analytics', 'overview', scope, anchor, lens], queryFn: () => api.get<Overview>('/analytics/overview', { scope, anchor, lens }), placeholderData: keepPreviousData })
}

export function useBreakdown(from: string, to: string, by: 'category' | 'tag' | 'task' | 'project' = 'category') {
  const lens = useLensStore((s) => s.lens)
  return useQuery({ queryKey: ['analytics', 'breakdown', from, to, by, lens], queryFn: () => api.get<Breakdown>('/analytics/breakdown', { from, to, by, lens }), placeholderData: keepPreviousData })
}

export function useTrends(metric: TrendMetric, granularity: 'day' | 'week', periods: number) {
  const lens = useLensStore((s) => s.lens)
  return useQuery({ queryKey: ['analytics', 'trends', metric, granularity, periods, lens], queryFn: () => api.get<Trends>('/analytics/trends', { metric, granularity, periods, lens }), placeholderData: keepPreviousData })
}
