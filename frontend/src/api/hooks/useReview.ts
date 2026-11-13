import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import type { CommitBody, CommitResult, Review } from '../types'

export const useReview = (entryId: string | undefined, jobId: string | undefined, enabled: boolean) =>
  useQuery({ queryKey: ['review', entryId, jobId], enabled: !!entryId && enabled, queryFn: () => api.get<Review>(`/journal-entries/${entryId}/review`, { job_id: jobId }) })

export function useAnswer(entryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (b: { job_id: string; question_id: string; value: string }) => api.post<Review>(`/journal-entries/${entryId}/review/answers`, b),
    onSuccess: (review, vars) => qc.setQueryData(['review', entryId, vars.job_id], review),
  })
}

export function useCommit(entryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ key, ...body }: CommitBody & { key: string }) =>
      api.post<CommitResult>(`/journal-entries/${entryId}/review/commit`, body, { headers: { 'Idempotency-Key': key } }),
    onSuccess: () => {
      for (const k of ['review', 'entries', 'entry', 'journal-stats', 'activities', 'timeline', 'tags', 'tasks', 'ideal', 'analytics']) qc.invalidateQueries({ queryKey: [k] })
    },
  })
}
