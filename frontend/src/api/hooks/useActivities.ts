import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, request } from '../client'
import { ACTIVITY_DEPENDENTS, qk } from '../queryKeys'
import type { Activity, ActivityCreate, ActivityDetail, ActivityEvent, ActivityPatch, DayTimeline, Timeline } from '../types'
import { toast } from '@/stores/toastStore'

export interface ActivityFilter {
  from?: string; to?: string; q?: string; category_id?: string; tag_ids?: string[]; tag_mode?: 'any' | 'all'
  task_id?: string; project_id?: string; kind?: 'actual' | 'planned'; certainty?: string; needs_review?: boolean
}

export function useTimeline(params: ActivityFilter & { from: string; to: string; ideal?: boolean }) {
  return useQuery({
    queryKey: qk.timeline(params), queryFn: async () => (await api.get<Timeline>('/timeline', params as any)).days as DayTimeline[],
    placeholderData: (prev) => prev,
  })
}

export function useActivitySearch(filter: ActivityFilter, enabled = true) {
  return useInfiniteQuery({
    queryKey: qk.activities(filter), enabled, initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => request<Activity[]>('/activities', { query: { ...(filter as any), limit: 30, cursor: pageParam } }),
    getNextPageParam: (last) => (last.meta.next_cursor as string | null | undefined) ?? undefined,
  })
}

export const useActivity = (id: string | undefined) =>
  useQuery({ queryKey: qk.activity(id ?? ''), enabled: !!id, queryFn: () => api.get<ActivityDetail>(`/activities/${id}`) })

export const useActivityEvents = (id: string | undefined) =>
  useQuery({ queryKey: qk.events(id ?? ''), enabled: !!id, queryFn: () => api.get<ActivityEvent[]>(`/activities/${id}/events`) })

function useActivityMutation<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of ACTIVITY_DEPENDENTS) qc.invalidateQueries({ queryKey: [key] })
    },
  })
}

export const useCreateActivity = () => useActivityMutation((b: ActivityCreate) => api.post<Activity>('/activities', b))
export const usePatchActivity = () => useActivityMutation(({ id, ...b }: ActivityPatch & { id: string }) => api.patch<Activity>(`/activities/${id}`, b))
export const useSplitActivity = () =>
  useActivityMutation(({ id, at }: { id: string; at: string }) => api.post<{ original: Activity; created: Activity }>(`/activities/${id}/split`, { at }))
export const useMergeActivities = () =>
  useActivityMutation((b: { activity_ids: string[]; category_id?: string; title?: string }) => api.post<Activity>('/activities/merge', b))
export const useDuplicateActivity = () => useActivityMutation(({ id, start_at }: { id: string; start_at?: string }) => api.post<Activity>(`/activities/${id}/duplicate`, { start_at }))
export const useSetActivityTags = () => useActivityMutation(({ id, tag_ids }: { id: string; tag_ids: string[] }) => api.put<Activity>(`/activities/${id}/tags`, { tag_ids }))
export const useRestoreActivity = () => useActivityMutation((id: string) => api.post<Activity>(`/activities/${id}/restore`))
export const useMarkDone = () => useActivityMutation(({ id, ...b }: { id: string; start_at?: string; end_at?: string }) => api.post<Activity>(`/activities/${id}/mark-done`, b))

/** Delete is soft, with a 10 s Undo toast (FR-060). */
export function useDeleteActivity() {
  const restore = useRestoreActivity()
  return useActivityMutation(async (id: string) => {
    await api.delete(`/activities/${id}`)
    toast.undo('Activity deleted', () => restore.mutate(id, { onError: () => toast.error('Could not restore: that time is taken now.') }))
  })
}
