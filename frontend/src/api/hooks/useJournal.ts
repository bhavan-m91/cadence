import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, request } from '../client'
import type { AiStatus, EntryDetail, EntryOut, EntryRevision, EntrySummary, JobOut, JournalStats } from '../types'

export interface EntryFilter { q?: string; status?: string; from?: string; to?: string }

export const useAiStatus = () => useQuery({ queryKey: ['ai-status'], queryFn: () => api.get<AiStatus>('/ai/status'), staleTime: 60_000 })
export const useJournalStats = () => useQuery({ queryKey: ['journal-stats'], queryFn: () => api.get<JournalStats>('/journal-entries/stats'), staleTime: 60_000 })

export function useRecentEntries(limit = 5) {
  return useQuery({ queryKey: ['entries', 'recent', limit], queryFn: () => api.get<EntrySummary[]>('/journal-entries', { limit }) })
}

export function useEntryList(filter: EntryFilter) {
  return useInfiniteQuery({
    queryKey: ['entries', 'list', filter], initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => request<EntrySummary[]>('/journal-entries', { query: { ...filter, limit: 20, cursor: pageParam } }),
    getNextPageParam: (last) => (last.meta.next_cursor as string | null | undefined) ?? undefined,
  })
}

export const useEntry = (id: string | undefined) =>
  useQuery({ queryKey: ['entry', id], enabled: !!id, queryFn: () => api.get<EntryDetail>(`/journal-entries/${id}`) })

export const useRevisions = (id: string | undefined, enabled = true) =>
  useQuery({ queryKey: ['entry', id, 'revisions'], enabled: !!id && enabled, queryFn: () => api.get<EntryRevision[]>(`/journal-entries/${id}/revisions`) })

function useEntryMutation<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of ['entries', 'entry', 'journal-stats']) qc.invalidateQueries({ queryKey: [key] })
    },
  })
}

export interface CreateEntry { raw_text: string; covers_start_at: string; covers_end_at: string; timezone: string; input_method: 'typed' | 'dictated'; dictation_seconds?: number | null }

export const useCreateEntry = () =>
  useEntryMutation((b: CreateEntry) => api.post<EntryOut>('/journal-entries', b))

export const usePatchEntry = () =>
  useEntryMutation(({ id, ...b }: { id: string; version: number; raw_text?: string; covers_start_at?: string; covers_end_at?: string; title?: string }) =>
    api.patch<EntryOut>(`/journal-entries/${id}`, b))

export const useDeleteEntry = () =>
  useEntryMutation(({ id, activities }: { id: string; activities?: 'keep' | 'delete' }) =>
    request<void>(`/journal-entries/${id}`, { method: 'DELETE', query: { activities } }))

export const useProcessEntry = () =>
  useEntryMutation(({ id, key, regenerate = false, user_hint }: { id: string; key: string; regenerate?: boolean; user_hint?: string }) =>
    api.post<{ job_id: string; status: string }>(`/journal-entries/${id}/process`, { regenerate, user_hint }, { headers: { 'Idempotency-Key': key } }))

const TERMINAL = ['succeeded', 'failed', 'cancelled']

/** Poll every 1.5 s until the job reaches a terminal state (FR-029). Pauses while offline. */
export function useJob(jobId: string | undefined) {
  return useQuery({
    queryKey: ['job', jobId], enabled: !!jobId, queryFn: () => api.get<JobOut>(`/ai-jobs/${jobId}`),
    refetchInterval: (q) => (q.state.data && TERMINAL.includes(q.state.data.status) ? false : navigator.onLine ? 1500 : false),
  })
}
