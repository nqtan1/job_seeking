import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SettingsPage } from '@/features/settings/SettingsPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn(), DELETE: vi.fn(), signOut: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))
vi.mock('@/lib/auth', () => ({ signOut: mocks.signOut }))

const renderPage = () => renderWithApp(<SettingsPage />)

beforeEach(() => {
  vi.clearAllMocks()
  mocks.signOut.mockResolvedValue(undefined)
  mocks.GET.mockImplementation(async (url: string) =>
    url === '/api/v1/me'
      ? { data: { user: { email: 'a@b.co' } } }
      : { data: { status: 'done', download_url: '/dl/export.zip' } },
  )
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
