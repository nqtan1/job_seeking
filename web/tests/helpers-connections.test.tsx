import '@/features/helpers/lib'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConnectionsTab } from '@/features/helpers/Connections'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn(), DELETE: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const view = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ConnectionsTab />
    </QueryClientProvider>,
  )

it('connects Telegram through a link, then can disconnect', async () => {
  const open = vi.spyOn(window, 'open').mockReturnValue(null)
  mocks.GET.mockResolvedValue({ data: { items: [], telegram_available: true } })
  mocks.POST.mockResolvedValue({ data: { url: 'https://t.me/bot?start=abc', expires_at: 'x' } })
  view()
  await userEvent.click(await screen.findByRole('button', { name: 'Connect Telegram' }))
  await waitFor(() =>
    expect(open).toHaveBeenCalledWith(
      'https://t.me/bot?start=abc',
      '_blank',
      'noopener,noreferrer',
    ),
  )
})

it('shows a connected account, and says when the server has no bot', async () => {
  mocks.GET.mockResolvedValue({
    data: {
      items: [{ provider: 'telegram', status: 'active', connected_at: null }],
      telegram_available: true,
    },
  })
  const { unmount } = view()
  expect(await screen.findByText('Connected')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Disconnect' })).toBeInTheDocument()
  unmount()

  mocks.GET.mockResolvedValue({ data: { items: [], telegram_available: false } })
  view()
  expect(await screen.findByText(/not available on this server/)).toBeInTheDocument()
})
