import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConsentBanner } from '@/features/radar/Consent'
import { LinkPage } from '@/features/radar/LinkPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), PUT: vi.fn(), POST: vi.fn(), DELETE: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))
vi.mock('@/lib/stepup', () => ({ ensureRecentAuth: vi.fn().mockResolvedValue(true) }))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.GET.mockImplementation(async (url: string) => {
    if (url === '/api/v1/radar/consent')
      return { data: { state: 'none', policy_version: 'v1', history: [] } }
    if (url === '/api/v1/radar/searches') return { data: [] }
    return { data: { session: { stepup_max_age_seconds: 300 } } }
  })
  mocks.PUT.mockResolvedValue({ data: { state: 'granted', policy_version: 'v1', history: [] } })
})

test('consent: unticked by default, the button stays disabled until ticked, then grants the shown version', async () => {
  const user = userEvent.setup()
  renderWithApp(<ConsentBanner />)
  await user.click(await screen.findByRole('button', { name: 'Review and enable' }))
  const enable = await screen.findByRole('button', { name: 'Enable background radars' })
  const box = screen.getByRole('checkbox', { name: /I agree/ })
  expect(box).not.toBeChecked()
  expect(enable).toBeDisabled()
  await user.click(box)
  expect(enable).toBeEnabled()
  await user.click(enable)
  await waitFor(() =>
    expect(mocks.PUT).toHaveBeenCalledWith('/api/v1/radar/consent', {
      body: { policy_version: 'v1' },
    }),
  )
})

test('the e-mail link page posts the fragment token and shows only a generic result', async () => {
  const user = userEvent.setup()
  window.location.hash = '#t=abc.def'
  const fetchMock = vi.fn().mockResolvedValue({ ok: true })
  vi.stubGlobal('fetch', fetchMock)
  renderWithApp(<LinkPage />)
  await user.click(screen.getByRole('button', { name: 'Stop background radars' }))
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/public/radar-link',
    expect.objectContaining({ body: JSON.stringify({ token: 'abc.def' }) }),
  )
  expect(await screen.findByText(/Done\. Your radars/)).toBeInTheDocument()
  vi.unstubAllGlobals()
})
