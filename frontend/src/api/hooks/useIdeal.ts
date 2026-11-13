import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import type { IdealOverview, IdealProgress, IdealTemplate } from '../types'

export const useIdeal = (kind: 'day' | 'week') =>
  useQuery({ queryKey: ['ideal', kind], queryFn: () => api.get<IdealOverview>(`/ideal/${kind}`), staleTime: 30_000 })

export const useIdealProgress = (scope: 'day' | 'week', on?: string) =>
  useQuery({ queryKey: ['ideal', 'progress', scope, on ?? null], queryFn: () => api.get<IdealProgress>('/ideal/progress', { scope, on }) })

export interface SaveIdealBody {
  kind: 'day' | 'week'
  effective_from: string
  allocations: { category_id: string; minutes: number; distribution?: 'all_days' | 'weekdays' | 'weekend' }[]
}

export function useSaveIdeal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, ...body }: SaveIdealBody) => api.put<IdealTemplate>(`/ideal/${kind}`, body),
    onSuccess: () => {
      for (const key of ['ideal', 'timeline', 'review']) qc.invalidateQueries({ queryKey: [key] })
    },
  })
}
