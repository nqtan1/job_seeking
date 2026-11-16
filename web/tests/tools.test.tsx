import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { ToolPage } from '@/features/tools/ToolPage'
import { ToolsPage } from '@/features/tools/ToolsPage'

const mocks = vi.hoisted(() => ({ GET: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))
vi.mock('@/features/settings/api', () => ({ useMe: () => ({ data: { helpers_enabled: true } }) }))

const tool = (id: string, pack: string, more: object = {}) => ({
  id,
  pack,
  inputs: [{ name: 'query', required: true }],
  outputs: ['items'],
  effect: 'read',
  ai_uses: 0,
  daily_cap: null,
  needs_job: false,
  chat: true,
  page: null,
  ...more,
})

test('packs from /tools with the career pages first, core hidden, search, then a tool page', async () => {
  mocks.GET.mockResolvedValue({
    data: [
      tool('wait', 'core'),
      tool('send_email', 'messages', { effect: 'outside', daily_cap: 20 }),
      tool('web_search', 'web', { ai_uses: 1 }),
      tool('fit_check', 'career', { page: '/jobs' }),
    ],
  })
  const router = createMemoryRouter(
    [
      { path: '/tools', element: <ToolsPage /> },
      { path: '/tools/:id', element: <ToolPage /> },
    ],
    { initialEntries: ['/tools'] },
  )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  const email = await screen.findByRole('link', { name: /Send an email/ })
  const career = screen.getByRole('region', { name: 'Career' })
  expect(
    within(career)
      .getAllByRole('link')
      .map((a) => a.getAttribute('href')),
  ).toEqual([
    '/jobs',
    '/tracker',
    '/profile', // fit_check has its own page (/jobs): reached through that card, not listed twice
  ])
  expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
    'Career',
    'Web',
    'Messages',
  ])
  expect(screen.queryByText('Wait')).not.toBeInTheDocument()
  expect(email).toHaveTextContent('20/day')
  expect(email).toHaveTextContent('Sends outside')
  expect(screen.getByRole('link', { name: /Search the web/ })).toHaveTextContent('AI')

  await userEvent.type(screen.getByRole('searchbox', { name: 'Search tools' }), 'email')
  expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
    'Messages',
  ])
  await userEvent.click(screen.getByRole('link', { name: /Send an email/ }))
  expect(await screen.findByRole('heading', { name: 'Send an email' })).toBeInTheDocument()
  expect(screen.getByText('query')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Use in a flow' })).toHaveAttribute(
    'href',
    '/automations',
  )
})
