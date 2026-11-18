import { screen, within } from '@testing-library/react'
import { TodayPage } from '@/features/today/TodayPage'
import { reminders } from '@/features/today/steps'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))
vi.mock('@/features/settings/api', () => ({ useMe: () => ({ data: {}, isPending: false }) }))

test('reminders: only what has a count, most urgent first', () => {
  expect(reminders({ followUps: 0, matches: 0 })).toEqual([])
  expect(reminders({ followUps: 2, matches: 4 }).map((r) => [r.key, r.to, r.count])).toEqual([
    ['follow_up', '/tracker', 2],
    ['matches', '/radar', 4],
  ])
})

test('Home shows the assistant inbox, newest first, each row opening its link', async () => {
  const msg = (id: string, kind: string, link: string, content: string) => ({
    id,
    role: 'assistant',
    content,
    created_at: new Date().toISOString(),
    meta: { inbox: { kind, link } },
  })
  mocks.GET.mockImplementation(async (url: string) => ({
    error: undefined,
    response: { status: 200 },
    data:
      url === '/api/v1/coach/assistant' || url === '/api/v1/profile'
        ? { id: 'as1' }
        : url.endsWith('/messages')
          ? [
              { id: 'u1', role: 'user', content: 'hi', created_at: '', meta: null }, // not inbox
              msg('m1', 'run_done', '/automations/runs/r1', 'Job hunter finished'),
              msg('m2', 'run_failed', 'https://evil.example', 'Follow-up failed'),
            ]
          : [],
  }))
  renderWithApp(<TodayPage />, { at: '/', path: '/' })

  const inbox = within(await screen.findByRole('region', { name: 'Inbox' }))
  const href = (name: RegExp) => inbox.getByRole('link', { name }).getAttribute('href')
  expect(inbox.getAllByRole('link')[0]).toHaveTextContent('Follow-up failed') // newest first
  expect(href(/Job hunter finished/)).toBe('/automations/runs/r1')
  expect(href(/Follow-up failed/)).toBe('/chat/as1') // not an app path: opens the conversation
  expect(href(/See all/)).toBe('/chat/as1')
  expect(inbox.queryByText('hi')).not.toBeInTheDocument()
  expect(screen.getByRole('form', { name: 'Ask your assistant' })).toBeInTheDocument()
})
