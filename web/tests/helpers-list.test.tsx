import '@/features/helpers/lib'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { inPlace, navFor } from '@/app/nav'
import { HelpersPage } from '@/features/helpers/HelpersPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))
vi.mock('@/features/settings/api', () => ({ useMe: () => ({ data: { helpers_enabled: true } }) }))

const tool = (id: string, chat: boolean) => ({
  id,
  pack: 'career',
  inputs: [],
  outputs: ['text'],
  effect: 'read',
  ai_uses: 0,
  daily_cap: null,
  needs_job: false,
  chat,
  page: null,
})

test('New helper asks for the type first and creates a built-in helper from the choice', async () => {
  mocks.GET.mockResolvedValue({ data: [], error: undefined })
  mocks.POST.mockResolvedValue({ data: { id: 'x1' }, error: undefined })
  const user = userEvent.setup()
  renderWithApp(<HelpersPage />, { at: '/helpers', path: '/helpers' })

  expect(await screen.findByText('No helper yet')).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: /^Use:/ })).toHaveLength(5) // templates stay
  await user.click(screen.getByRole('button', { name: 'New helper' }))
  for (const n of ['Cover letter', 'Interview prep', 'CV advice', 'Write my own'])
    expect(screen.getByRole('button', { name: new RegExp(n) })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /Interview prep/ }))
  await waitFor(() => expect(mocks.POST).toHaveBeenCalled())
  expect(mocks.POST.mock.calls[0]?.[1].body).toMatchObject({
    name: 'Interview prep',
    spec: { role: 'interview', instructions: '' },
  })
})

test('agents are cards: the Coach first with its chat tools, then each agent with Chat and Edit', async () => {
  mocks.GET.mockImplementation(async (url: string) => ({
    data:
      url === '/api/v1/tools'
        ? [tool('web_search', true), tool('send_email', false), tool('save_note', true)]
        : [
            {
              id: 'a1',
              name: 'Mira',
              description: 'Follow-ups',
              avatar: { seed: 'a1', body: 0, palette: 0, eyes: 0, accessory: 0 },
              current_version: 2,
              archived: false,
              created_at: '',
              updated_at: '',
              tools: ['save_note'], // the list carries each agent's chat tools: one request
            },
          ],
  }))
  renderWithApp(<HelpersPage />, { at: '/helpers', path: '/helpers' })

  await screen.findByText('Mira')
  const [coach, mira] = [...screen.getByRole('list', { name: 'Agents' }).children] as HTMLElement[]
  expect(within(coach).getByRole('link', { name: 'Chat: Coach' })).toHaveAttribute('href', '/chat')
  // the coach's own tools; an agent's tools from the list, a new pack tool by its id
  await waitFor(() =>
    expect(within(coach).getByRole('list', { name: 'Tools' })).toHaveTextContent(
      /^Search the web$/,
    ),
  )
  expect(await within(mira).findByText('save_note')).toBeInTheDocument()
  expect(within(mira).getByRole('link', { name: 'Chat: Mira' })).toHaveAttribute(
    'href',
    '/chat?agent=a1',
  )
  expect(within(mira).getByRole('link', { name: 'Edit: Mira' })).toHaveAttribute(
    'href',
    '/helpers/a1',
  )
  // a run page sits under /automations but is lit as Activity
  const lit = navFor({ helpers_enabled: true }).filter((p) => inPlace(p, '/automations/runs/r1'))
  expect(lit.map((p) => p.to)).toEqual(['/activity'])
})
