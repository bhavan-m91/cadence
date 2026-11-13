import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { qk } from '../queryKeys'
import type { Category, CategoryNode, KeywordRule, Tag, TagDetail } from '../types'

export function useCategories(archived = false) {
  return useQuery({ queryKey: qk.categories(archived), queryFn: () => api.get<CategoryNode[]>('/categories', { include_archived: archived }), staleTime: 60_000 })
}

export interface FlatCategory extends CategoryNode { label: string }

export function flattenCategories(nodes: CategoryNode[] | undefined, includeArchived = false): FlatCategory[] {
  const out: FlatCategory[] = []
  const walk = (list: CategoryNode[]) => list.forEach((n) => {
    if (includeArchived || !n.archived) out.push({ ...n, label: n.path_names })
    walk(n.children ?? [])
  })
  walk(nodes ?? [])
  return out
}

export const categoryMap = (nodes: CategoryNode[] | undefined) => new Map(flattenCategories(nodes, true).map((c) => [c.id, c]))

export function useTags(params: { archived?: boolean; q?: string; from?: string; to?: string } = {}) {
  return useQuery({ queryKey: qk.tags(params), queryFn: () => api.get<Tag[]>('/tags', params), staleTime: 30_000 })
}

export function useTag(id: string | undefined, params: { from?: string; to?: string } = {}) {
  return useQuery({ queryKey: qk.tag(id ?? '', params), enabled: !!id, queryFn: () => api.get<TagDetail>(`/tags/${id}`, params) })
}

export function useRules(params: { target_type?: string; target_id?: string } = {}) {
  return useQuery({ queryKey: qk.rules(params), queryFn: () => api.get<KeywordRule[]>('/keyword-rules', params) })
}

/** Taxonomy edits can change names/colours shown on every activity, so everything derived refreshes. */
function useTaxonomyMutation<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of ['categories', 'tags', 'tag', 'rules', 'activities', 'activity', 'timeline', 'tasks']) qc.invalidateQueries({ queryKey: [key] })
    },
  })
}

export const useCreateCategory = () =>
  useTaxonomyMutation((b: { parent_id: string; name: string; color?: string; description?: string; counts_as_focus?: boolean }) => api.post<Category>('/categories', b))
export const useUpdateCategory = () =>
  useTaxonomyMutation(({ id, ...b }: { id: string; name?: string; color?: string; description?: string | null; counts_as_focus?: boolean; parent_id?: string; archived?: boolean }) =>
    api.patch<Category>(`/categories/${id}`, b))
export const useDeleteCategory = () => useTaxonomyMutation((id: string) => api.delete(`/categories/${id}`))
export const useMergeCategory = () =>
  useTaxonomyMutation(({ id, target_id, preview = false }: { id: string; target_id: string; preview?: boolean }) =>
    api.post<{ moved_activities: number; moved_allocations: number; preview: boolean }>(`/categories/${id}/merge`, { target_id, preview }))

export const useCreateTag = () =>
  useTaxonomyMutation((b: { name: string; color?: string; description?: string; goal_kind?: string; goal_weekly_minutes?: number | null }) => api.post<Tag>('/tags', b))
export const useUpdateTag = () =>
  useTaxonomyMutation(({ id, ...b }: { id: string; name?: string; color?: string; description?: string | null; goal_kind?: string; goal_weekly_minutes?: number | null; archived?: boolean; keep_old_name_as_alias?: boolean }) =>
    api.patch<Tag>(`/tags/${id}`, b))
export const useDeleteTag = () => useTaxonomyMutation((id: string) => api.delete(`/tags/${id}`))
export const useMergeTag = () =>
  useTaxonomyMutation(({ id, target_id, preview = false }: { id: string; target_id: string; preview?: boolean }) =>
    api.post<{ moved_links: number; deduplicated: number; preview: boolean }>(`/tags/${id}/merge`, { target_id, preview }))
export const usePutAliases = () => useTaxonomyMutation(({ id, aliases }: { id: string; aliases: string[] }) => api.put<string[]>(`/tags/${id}/aliases`, { aliases }))
export const useCreateRule = () =>
  useTaxonomyMutation((b: { phrase: string; target_type: 'tag' | 'category'; target_id: string }) => api.post<KeywordRule>('/keyword-rules', b))
export const useDeleteRule = () => useTaxonomyMutation((id: string) => api.delete(`/keyword-rules/${id}`))
