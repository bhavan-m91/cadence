export const qk = {
  me: ['me'] as const,
  preferences: ['preferences'] as const,
  authEvents: ['auth-events'] as const,
  categories: (archived = false) => ['categories', { archived }] as const,
  tags: (params?: object) => ['tags', params ?? {}] as const,
  tag: (id: string, params?: object) => ['tag', id, params ?? {}] as const,
  rules: (params?: object) => ['rules', params ?? {}] as const,
  tasks: (params?: object) => ['tasks', params ?? {}] as const,
  task: (id: string) => ['task', id] as const,
  projects: (archived?: boolean) => ['projects', { archived }] as const,
  activities: (params?: object) => ['activities', params ?? {}] as const,
  activity: (id: string) => ['activity', id] as const,
  events: (id: string) => ['events', id] as const,
  timeline: (params: object) => ['timeline', params] as const,
  exportJob: (id: string) => ['export', id] as const,
}

/** Everything derived from activities must refresh after a write (slices change coverage, tag totals, task rollups). */
export const ACTIVITY_DEPENDENTS = ['activities', 'activity', 'events', 'timeline', 'tags', 'tag', 'tasks', 'task', 'projects'] as const
