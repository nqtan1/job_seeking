import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AdminAiPage } from '@/features/admin/AdminAiPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const feature = (over: object) => ({
  feature: 'fit',
  provider: 'gemini',
  model: 'gemini-2.5-flash',
  default: 'gemini/gemini-2.5-flash',
  overridden: false,
  prompt_version: 'fit@1',
  calls: 12,
  errors: 1,
  avg_latency_ms: 800,
  p95_latency_ms: 2100,
  input_tokens: 1000,
  output_tokens: 200,
  ...over,
})

let overridden = false
beforeEach(() => {
  vi.clearAllMocks()
  overridden = false
  mocks.GET.mockImplementation(async () => ({
    data: {
      features: [feature(overridden ? { model: 'gemini-2.5-pro', overridden: true } : {})],
      allowed_models: { gemini: ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.5-pro'] },
      changes: [],
    },
  }))
})

const renderPage = () => renderWithApp(<AdminAiPage />, { at: '/admin/ai', path: '/admin/ai' })

test('shows usage per feature and changes the model with one PUT', async () => {
  const user = userEvent.setup()
  mocks.PUT.mockResolvedValue({ data: undefined })
  renderPage()

  expect(await screen.findByText('fit@1')).toBeInTheDocument()
  expect(screen.getByText('2,100')).toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Model for fit'), 'gemini/gemini-2.5-pro')

  await waitFor(() =>
    expect(mocks.PUT).toHaveBeenCalledWith('/api/v1/admin/ai/{feature}', {
      params: { path: { feature: 'fit' } },
      body: { provider: 'gemini', model: 'gemini-2.5-pro' },
    }),
  )
})

test('an overridden feature shows its default and can be reset', async () => {
  const user = userEvent.setup()
  overridden = true
  mocks.DELETE.mockResolvedValue({ data: undefined })
  renderPage()

  expect(
    await screen.findByText(/Overridden · default gemini\/gemini-2.5-flash/),
  ).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Reset fit to default' }))

  await waitFor(() =>
    expect(mocks.DELETE).toHaveBeenCalledWith('/api/v1/admin/ai/{feature}', {
      params: { path: { feature: 'fit' } },
    }),
  )
})
