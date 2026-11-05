import '@/features/helpers/lib'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { RouterProvider, createMemoryRouter } from 'react-router'
import { AutomationsPage } from '@/features/helpers/AutomationsPage'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn(), DELETE: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

it.each(['contacts', 'connections'])(
  '?tab=%s lands on Accounts (Telegram + email)',
  async (tab) => {
    mocks.GET.mockImplementation(async (url: string) => ({
      data: url === '/api/v1/connections' ? { items: [], telegram_available: true } : [],
    }))
    const router = createMemoryRouter([{ path: '/automations', element: <AutomationsPage /> }], {
      initialEntries: [`/automations?tab=${tab}`],
    })
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    expect(await screen.findByRole('button', { name: 'Connect Telegram' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Email' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Accounts' })).toHaveAttribute('aria-current', 'page')
  },
)
