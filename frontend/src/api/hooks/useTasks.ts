import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { qk } from '../queryKeys'
import type { Project, Task, TaskDetail } from '../types'

export function useTasks(params: { status?: string; project_id?: string; q?: string; priority?: number; has_time?: boolean } = {}) {
  return useQuery({ queryKey: qk.tasks(params), queryFn: () => api.get<Task[]>('/tasks', { ...params, limit: 100 }) })
}

export const useTask = (id: string | undefined) =>
  useQuery({ queryKey: qk.task(id ?? ''), enabled: !!id, queryFn: () => api.get<TaskDetail>(`/tasks/${id}`) })

export const useProjects = (archived?: boolean) =>
  useQuery({ queryKey: qk.projects(archived), queryFn: () => api.get<Project[]>('/projects', { archived }), staleTime: 30_000 })

function useWriteMutation<V, R>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of ['tasks', 'task', 'projects', 'activity', 'activities', 'analytics']) qc.invalidateQueries({ queryKey: [key] })
    },
  })
}

export const useCreateTask = () =>
  useWriteMutation((b: { title: string; description?: string; project_id?: string | null; priority?: number | null; due_date?: string | null; estimate_minutes?: number | null }) => api.post<Task>('/tasks', b))
export const useUpdateTask = () =>
  useWriteMutation(({ id, ...b }: { id: string; version?: number; title?: string; description?: string; project_id?: string | null; priority?: number | null; due_date?: string | null; status?: string; estimate_minutes?: number | null; clear?: string[] }) =>
    api.patch<Task>(`/tasks/${id}`, b))
export const useDeleteTask = () => useWriteMutation((id: string) => api.delete(`/tasks/${id}`))
export const useCreateProject = () => useWriteMutation((b: { name: string; color?: string }) => api.post<Project>('/projects', b))
export const useUpdateProject = () => useWriteMutation(({ id, ...b }: { id: string; name?: string; color?: string; archived?: boolean }) => api.patch<Project>(`/projects/${id}`, b))
