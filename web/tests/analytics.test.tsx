import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const ph = vi.hoisted(() => ({
  imported: false,
  init: vi.fn(),
  capture: vi.fn(),
  opt_out_capturing: vi.fn(),
  reset: vi.fn(),
}))
vi.mock('posthog-js', () => {
  ph.imported = true
  return { default: ph }
})

const fresh = async () => {
  vi.resetModules()
  return import('@/lib/analytics')
}
const flush = () => new Promise((r) => setTimeout(r, 0))

beforeEach(() => {
  localStorage.clear()
  vi.stubEnv('VITE_POSTHOG_KEY', 'phc_synthetic')
  ph.imported = false
  ph.init.mockClear()
  ph.capture.mockClear()
})
afterEach(() => vi.unstubAllEnvs())

test('declining in the banner means PostHog is never loaded', async () => {
  const { AnalyticsBanner } = await import('@/features/settings/Analytics')
  render(<AnalyticsBanner />)
  await userEvent.click(screen.getByRole('button', { name: 'No thanks' }))
  expect(screen.queryByRole('button', { name: 'Accept' })).not.toBeInTheDocument()

  const { track } = await fresh()
  track('job_added')
  await flush()
  expect(ph.imported).toBe(false)
})

test('after consent PostHog starts with the safe options and sends the bare event', async () => {
  localStorage.setItem('analytics-consent', 'yes')
  const { track } = await fresh()
  track('letter_made')
  await vi.waitFor(() => expect(ph.capture).toHaveBeenCalledWith('letter_made'))
  expect(ph.init).toHaveBeenCalledWith(
    'phc_synthetic',
    expect.objectContaining({
      api_host: 'https://eu.i.posthog.com',
      autocapture: false,
      capture_pageview: false,
      disable_session_recording: true,
      persistence: 'localStorage',
      person_profiles: 'identified_only',
    }),
  )
  const { before_send } = ph.init.mock.calls[0][1]
  const id = '0b5f4f3e-1c2d-4e5f-8a9b-0c1d2e3f4a5b'
  const e = before_send({ properties: { $current_url: `https://x.test/jobs/${id}?q=secret` } })
  expect(e.properties.$current_url).toBe('https://x.test/jobs/:id')

  // a later "no" stops the loaded SDK and wipes its stored id
  const { setConsent } = await import('@/lib/analytics')
  setConsent('no')
  await vi.waitFor(() => expect(ph.reset).toHaveBeenCalled())
  expect(ph.opt_out_capturing).toHaveBeenCalled()
})

test('the API middleware maps successful POSTs to events, not GETs or failures', async () => {
  localStorage.setItem('analytics-consent', 'yes')
  const { analyticsMiddleware } = await fresh()
  const call = (method: string, schemaPath: string, status = 200, body: unknown = {}) =>
    analyticsMiddleware.onResponse!({
      request: new Request('https://x.test/', { method }),
      schemaPath,
      response: new Response(JSON.stringify(body), { status }),
    } as never)

  await call('GET', '/api/v1/jobs')
  await call('POST', '/api/v1/jobs', 422)
  await call('POST', '/api/v1/applications', 201, { status: 'to_apply' })
  await flush()
  expect(ph.capture).not.toHaveBeenCalled()

  await call('POST', '/api/v1/jobs', 201)
  await call('POST', '/api/v1/applications/{application_id}/status', 200, { status: 'applied' })
  await vi.waitFor(() => expect(ph.capture.mock.calls).toEqual([['job_added'], ['applied']]))
})
