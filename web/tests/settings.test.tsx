import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SettingsPage } from '@/features/settings/SettingsPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PUT: vi.fn(),
  DELETE: vi.fn(),
  signOut: vi.fn(),
}))
vi.mock('@/lib/api/client', () => ({ api: mocks }))
vi.mock('@/lib/auth', () => ({
  signOut: mocks.signOut,
  signInAgeSeconds: async () => 0,
  signInMethods: () => ({ email: 'a@b.co', verified: true, google: true, password: true }),
}))

const renderPage = () => renderWithApp(<SettingsPage />)

beforeEach(() => {
  vi.clearAllMocks()
  mocks.signOut.mockResolvedValue(undefined)
  mocks.GET.mockImplementation(async (url: string) => {
    if (url === '/api/v1/me')
      return { data: { user: { email: 'a@b.co' }, session: { stepup_max_age_seconds: 300 } } }
    if (url === '/api/v1/radar/consent')
      return { data: { state: 'none', policy_version: 'v1', history: [] } }
    if (url === '/api/v1/me/ai-calls') return { data: [] }
    if (url === '/api/v1/profile/memory')
      return { data: { facts: [{ id: 'f1', text: 'Lives in Lyon', created_at: '2026-11-01' }] } }
    return { data: { status: 'done', download_url: '/dl/export.zip' } }
  })
})

test('export: request → task polled → a download link appears', async () => {
  const user = userEvent.setup()
  mocks.POST.mockResolvedValue({ data: { task_id: 't1' } })
  renderPage()
  expect(await screen.findByText('Signed in as a@b.co')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Request export' }))
  const link = await screen.findByRole('link', { name: /Download your export/ })
  expect(link).toHaveAttribute('href', '/dl/export.zip')
})

test('delete stays disabled until DELETE is typed, then deletes and signs out', async () => {
  const user = userEvent.setup()
  mocks.DELETE.mockResolvedValue({})
  renderPage()
  const button = await screen.findByRole('button', { name: 'Delete my account' })
  expect(button).toBeDisabled()
  await user.type(screen.getByLabelText(/Type DELETE/), 'delete')
  expect(button).toBeDisabled()
  await user.clear(screen.getByLabelText(/Type DELETE/))
  await user.type(screen.getByLabelText(/Type DELETE/), 'DELETE')
  await user.click(button)
  await waitFor(() => expect(mocks.DELETE).toHaveBeenCalledWith('/api/v1/me'))
  await waitFor(() => expect(mocks.signOut).toHaveBeenCalled())
})

test('a failed deletion shows the error and does not sign out', async () => {
  const user = userEvent.setup()
  mocks.DELETE.mockResolvedValue({ error: { detail: 'Please sign in again.', request_id: 'rq3' } })
  renderPage()
  await user.type(await screen.findByLabelText(/Type DELETE/), 'DELETE')
  await user.click(screen.getByRole('button', { name: 'Delete my account' }))
  expect(await screen.findByText(/sign in again\. \(request id: rq3\)/)).toBeInTheDocument()
  expect(mocks.signOut).not.toHaveBeenCalled()
})

test('memory: editing a fact saves the full list with PUT', async () => {
  const user = userEvent.setup()
  mocks.PUT.mockImplementation(async (_url: string, init: { body: unknown }) => ({
    data: init.body,
  }))
  renderPage()
  expect(await screen.findByText('Lives in Lyon')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Edit “Lives in Lyon”' }))
  const input = screen.getByRole('textbox', { name: 'Edit “Lives in Lyon”' })
  await user.clear(input)
  await user.type(input, 'Lives in Paris{Enter}')
  expect(mocks.PUT).toHaveBeenCalledWith('/api/v1/profile/memory', {
    body: { facts: [{ id: 'f1', text: 'Lives in Paris', created_at: '2026-11-01' }] },
  })
  expect(await screen.findByText('Lives in Paris')).toBeInTheDocument()
  expect(screen.getByText('1/30')).toBeInTheDocument()
})
