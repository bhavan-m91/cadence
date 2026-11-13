/** The only layer that talks HTTP: bearer token, one silent refresh on 401, typed errors (PRD 8.4). */
import { useAuthStore } from '@/stores/authStore'
import type { Meta } from './types'

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''
const PREFIX = `${BASE}/api/v1`

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, any> = {},
    public requestId: string | null = null,
    public retryAfter: number | null = null,
  ) {
    super(message)
  }
}

type Query = Record<string, string | number | boolean | null | undefined | (string | number)[]>

function qs(query?: Query): string {
  if (!query) return ''
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) v.forEach((x) => p.append(k, String(x)))
    else p.set(k, String(v))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

let refreshing: Promise<boolean> | null = null

/** Single-flight refresh so parallel 401s share one rotation. */
export function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch(`${PREFIX}/auth/refresh`, { method: 'POST', credentials: 'include' })
      .then(async (r) => {
        if (!r.ok) return false
        const body = await r.json()
        useAuthStore.getState().setToken(body.data.access_token)
        return true
      })
      .catch(() => false)
      .finally(() => {
        refreshing = null
      })
  }
  return refreshing
}

interface Options {
  method?: string
  query?: Query
  body?: unknown
  auth?: boolean
  signal?: AbortSignal
  headers?: Record<string, string>
}

async function send(path: string, o: Options): Promise<Response> {
  const token = useAuthStore.getState().accessToken
  const headers: Record<string, string> = { Accept: 'application/json', ...o.headers }
  if (o.body !== undefined) headers['Content-Type'] = 'application/json'
  if (o.auth !== false && token) headers.Authorization = `Bearer ${token}`
  return fetch(`${PREFIX}${path}${qs(o.query)}`, {
    method: o.method ?? 'GET', headers, credentials: 'include', signal: o.signal,
    body: o.body !== undefined ? JSON.stringify(o.body) : undefined,
  })
}

export async function request<T>(path: string, o: Options = {}): Promise<{ data: T; meta: Meta }> {
  let res = await send(path, o)
  if (res.status === 401 && o.auth !== false && !path.startsWith('/auth/')) {
    if (await refreshSession()) res = await send(path, o)
    else useAuthStore.getState().clear()
  }
  if (res.status === 204) return { data: undefined as T, meta: {} }
  let json: any = null
  try {
    json = await res.json()
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const e = json?.error
    throw new ApiError(res.status, e?.code ?? 'HTTP_ERROR', e?.message ?? res.statusText, e?.details ?? {}, e?.request_id ?? null,
      Number(res.headers.get('Retry-After')) || null)
  }
  return { data: json.data as T, meta: (json.meta ?? {}) as Meta }
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>(path, { query, signal }).then((r) => r.data),
  list: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T[]>(path, { query, signal }),
  post: <T>(path: string, body?: unknown, o: Options = {}) => request<T>(path, { ...o, method: 'POST', body: body ?? {} }).then((r) => r.data),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body }).then((r) => r.data),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body }).then((r) => r.data),
  delete: (path: string, body?: unknown) => request<void>(path, { method: 'DELETE', body }).then(() => undefined),
}
