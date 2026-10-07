import { api } from '@/lib/api/client'

vi.mock('@/lib/auth', () => ({ getAuthHeaders: async () => ({ Authorization: 'Bearer tok' }) }))
vi.mock('@/lib/app-check', () => ({
  getAppCheckHeaders: async () => ({ 'X-Firebase-AppCheck': 'ac' }),
}))

test('typed GET /api/v1/me carries the ID token and App Check headers', async () => {
  const fetchMock = vi.fn(async (_req: Request) => Response.json({ id: 'u1' }))
  const { data } = await api.GET('/api/v1/me', { fetch: fetchMock })
  const req = fetchMock.mock.calls[0][0]
  expect(new URL(req.url).pathname).toBe('/api/v1/me')
  expect(req.headers.get('authorization')).toBe('Bearer tok')
  expect(req.headers.get('x-firebase-appcheck')).toBe('ac')
  expect(data).toBeDefined()
})

describe('streamMessage', () => {
  const sse = (body: string, ok = true) =>
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(body, { status: ok ? 200 : 422 })),
    )

  test('reads token events until done', async () => {
    const { streamMessage } = await import('@/features/coach/api')
    sse(
      'event: token\ndata: {"text": "Hi "}\n\nevent: token\ndata: {"text": "you"}\n\nevent: done\ndata: {}\n\n',
    )
    const got: string[] = []
    await streamMessage('c', 'x', (t) => got.push(t))
    expect(got.join('')).toBe('Hi you')
  })

  test('an error event or a refusal throws a safe problem', async () => {
    const { streamMessage } = await import('@/features/coach/api')
    sse(
      'event: token\ndata: {"text": "a"}\n\nevent: error\ndata: {"code": "x", "detail": "Nope."}\n\n',
    )
    await expect(streamMessage('c', 'x', () => {})).rejects.toEqual({ detail: 'Nope.' })
    sse('{"detail": "Upload your CV first."}', false)
    await expect(streamMessage('c', 'x', () => {})).rejects.toEqual({
      detail: 'Upload your CV first.',
    })
  })
})
