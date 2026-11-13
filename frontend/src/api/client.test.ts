import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import { api, ApiError } from './client'
import { errorMessage } from './errors'

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } })

describe('api client', () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    useAuthStore.setState({ status: 'authed', accessToken: 'old', user: null })
  })
  afterEach(() => { fetchMock.mockReset(); vi.unstubAllGlobals() })

  it('sends the bearer token and unwraps the data envelope', async () => {
    fetchMock.mockResolvedValueOnce(json(200, { data: { id: 1 }, meta: {} }))
    expect(await api.get('/things', { a: 1, b: undefined, c: ['x', 'y'] })).toEqual({ id: 1 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/things?a=1&c=x&c=y')
    expect(init.headers.Authorization).toBe('Bearer old')
  })

  it('refreshes once on 401 and retries with the new token', async () => {
    fetchMock
      .mockResolvedValueOnce(json(401, { error: { code: 'TOKEN_EXPIRED', message: 'x', details: {} } }))
      .mockResolvedValueOnce(json(200, { data: { access_token: 'new' } }))
      .mockResolvedValueOnce(json(200, { data: 'ok', meta: {} }))
    expect(await api.get('/things')).toBe('ok')
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe('Bearer new')
    expect(useAuthStore.getState().accessToken).toBe('new')
  })

  it('shares one refresh between parallel 401s (single flight)', async () => {
    let refreshes = 0
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
      if (url.endsWith('/auth/refresh')) { refreshes++; return json(200, { data: { access_token: 'new' } }) }
      return (init.headers as Record<string, string>).Authorization === 'Bearer new' ? json(200, { data: 'ok', meta: {} }) : json(401, { error: { code: 'TOKEN_EXPIRED', message: 'x' } })
    })
    await Promise.all([api.get('/a'), api.get('/b'), api.get('/c')])
    expect(refreshes).toBe(1)
  })

  it('signs the user out when the refresh fails', async () => {
    fetchMock.mockResolvedValueOnce(json(401, { error: { code: 'UNAUTHENTICATED', message: 'x' } })).mockResolvedValueOnce(json(401, {}))
    await expect(api.get('/things')).rejects.toBeInstanceOf(ApiError)
    expect(useAuthStore.getState().status).toBe('anon')
    expect(useAuthStore.getState().accessToken).toBeNull()
  })

  it('turns an error envelope into a typed ApiError with friendly text', async () => {
    fetchMock.mockResolvedValueOnce(json(409, { error: { code: 'ACTIVITY_OVERLAP', message: 'Overlaps', details: { conflicts: [] }, request_id: 'r1' } }))
    const err = await api.post('/activities', {}).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 409, code: 'ACTIVITY_OVERLAP', requestId: 'r1' })
    expect(errorMessage(err)).toBe('That overlaps another activity.')
  })

  it('does not try to refresh failed logins and reports the retry time on 429', async () => {
    fetchMock.mockResolvedValueOnce(json(429, { error: { code: 'RATE_LIMITED', message: 'slow down' } }, { 'Retry-After': '600' }))
    const err = await api.post('/auth/login', {}, { auth: false }).catch((e) => e)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(errorMessage(err)).toContain('10 min')
  })

  it('handles 204 with no body', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await expect(api.delete('/things/1')).resolves.toBeUndefined()
  })
})
