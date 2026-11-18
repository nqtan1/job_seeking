import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatPage } from '@/features/coach/ChatPage'
import { createConversation, decideAction, streamMessage } from '@/features/coach/api'
import { askCoachUrl } from '@/features/coach/link'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({
  profile: { data: { id: 'p' } as unknown, isPending: false },
  finish: () => {},
  messages: undefined as unknown,
}))
vi.mock('@/features/candidate/api', () => ({ useProfile: () => mocks.profile }))
vi.mock('@/features/job-search/api', () => ({
  useJobs: () => ({
    data: [{ id: 'j1', data: { title: 'AI Engineer', company: { name: 'Acme' } } }],
  }),
}))
vi.mock('@/features/helpers/api', () => ({
  useAgent: (id?: string) => ({
    data: id && {
      name: 'Mira',
      avatar: { seed: 'a1', body: 0, palette: 0, eyes: 0, accessory: 0 },
    },
  }),
}))
vi.mock('@/features/coach/api', () => ({
  useConversation: () => ({ data: undefined }),
  useDeleteConversation: () => ({ mutate: vi.fn(), isPending: false }),
  useSetFocus: () => ({ mutate: vi.fn(), isPending: false }),
  useMessages: () => ({ data: mocks.messages, isLoading: false, isPending: true }),
  createConversation: vi.fn(async () => ({ id: 'c1' })),
  regenerateReply: vi.fn(),
  decideAction: vi.fn(async (_c: string, _a: string, d: string) => ({
    status: d === 'confirm' ? 'done' : 'cancelled',
    code: null,
  })),
  streamMessage: vi.fn(
    async (
      _id: string,
      _text: string,
      onEvent: (n: string, d: Record<string, unknown>) => void,
    ) => {
      onEvent('context', { job: { title: 'AI Engineer', chars: 1134, truncated: false } })
      onEvent('step', { id: '1.0', tool: 'get_job', label: 'Reading the job', status: 'done' })
      onEvent('token', { text: 'Hello **' })
      onEvent('token', { text: 'there**' })
      onEvent('notice', { code: 'web_unavailable' })
      await new Promise<void>((resolve) => (mocks.finish = resolve))
    },
  ),
}))

test('without a profile the coach asks for the CV first', () => {
  mocks.profile = { data: null, isPending: false }
  renderWithApp(<ChatPage />, { at: '/', path: '/' })
  expect(screen.getByRole('link', { name: 'Upload your CV' })).toHaveAttribute('href', '/profile')
})

test('a suggestion starts a conversation and streams the reply', async () => {
  mocks.profile = { data: { id: 'p' }, isPending: false }
  renderWithApp(<ChatPage />, { at: '/', path: '/' })
  await userEvent.click(screen.getByRole('button', { name: 'Review my CV' }))
  expect(await screen.findByText('there', { selector: 'strong' })).toBeInTheDocument()
  expect(streamMessage).toHaveBeenCalledWith(
    'c1',
    expect.stringContaining('Review my CV'),
    expect.any(Function),
    expect.any(AbortSignal),
  )
  // what the coach did and what it had in context are visible, and degraded modes are said
  expect(screen.getByText('Reading the job')).toBeInTheDocument()
  expect(screen.getByText(/1,134 characters/)).toBeInTheDocument()
  expect(screen.getByText('Web research is unavailable with this model.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()
  mocks.finish()
})

test('"Discuss this job" opens a chat focused on that job, the draft in the box', async () => {
  mocks.profile = { data: { id: 'p' }, isPending: false }
  renderWithApp(<ChatPage />, { at: askCoachUrl('j1', 'Help me prepare'), path: '/chat' })
  expect(await screen.findByText('AI Engineer')).toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: /message/i })).toHaveValue('Help me prepare')
  await userEvent.click(screen.getByRole('button', { name: 'Review my CV' }))
  expect(createConversation).toHaveBeenCalledWith({ job_id: 'j1', agent_id: null })
  mocks.finish()
})

test('"Chat" on an agent card opens a chat with that agent', async () => {
  mocks.profile = { data: { id: 'p' }, isPending: false }
  renderWithApp(<ChatPage />, { at: '/chat?agent=a1', path: '/chat' })
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Mira')
  await userEvent.click(screen.getByRole('button', { name: 'Review my CV' }))
  expect(createConversation).toHaveBeenLastCalledWith({ job_id: null, agent_id: 'a1' })
  mocks.finish()
})

test('a suggested action runs only on "Confirm", and "Cancel" drops it', async () => {
  mocks.profile = { data: { id: 'p' }, isPending: false }
  const proposal = (id: string, summary: string, untrusted: boolean) => ({
    action_id: id,
    tool: 'add_to_tracker',
    summary,
    args: {},
    untrusted,
  })
  vi.mocked(streamMessage).mockImplementationOnce(async (_id, _text, onEvent) => {
    onEvent('proposal', proposal('a1', 'Add AI Engineer at Acme to your tracker', true))
    onEvent('proposal', proposal('a2', 'Add Data Analyst at Beta to your tracker', false))
    mocks.messages = [
      { id: 'u1', role: 'user', content: 'Save both jobs', meta: null },
      { id: 'm1', role: 'assistant', content: 'Confirm below.', meta: null },
    ]
    onEvent('done', { message_id: 'm1' })
  })
  renderWithApp(<ChatPage />, { at: '/chat/c1', path: '/chat/:conversationId' })
  await userEvent.type(screen.getByRole('textbox', { name: /message/i }), 'Save both jobs{Enter}')

  const [first, second] = await screen.findAllByRole('region', { name: /^Suggested action/ })
  expect(first).toHaveAccessibleName('Suggested action Add AI Engineer at Acme to your tracker')
  expect(within(first).getByRole('note')).toHaveTextContent('Suggested from outside content')
  expect(within(second).queryByRole('note')).toBeNull()
  expect(decideAction).not.toHaveBeenCalled()

  await userEvent.click(within(first).getByRole('button', { name: 'Confirm' }))
  expect(await within(first).findByRole('status')).toHaveTextContent('Done')
  expect(within(first).queryByRole('button')).toBeNull()
  await userEvent.click(within(second).getByRole('button', { name: 'Cancel' }))
  expect(await within(second).findByText(/Cancelled/)).toBeInTheDocument()
  expect(decideAction).toHaveBeenCalledWith('c1', 'a1', 'confirm')
  expect(decideAction).toHaveBeenCalledWith('c1', 'a2', 'cancel')
  mocks.messages = undefined
})

test('after a reload the cards come back from meta.actions with their stored status', () => {
  mocks.profile = { data: { id: 'p' }, isPending: false }
  const card = (id: string, status: string, tool: string, args = {}) => ({
    action_id: id,
    tool,
    summary: `Summary ${id}`,
    args,
    untrusted: false,
    status,
    code: status === 'failed' ? 'routine_not_found' : null,
  })
  mocks.messages = [
    {
      id: 'm1',
      role: 'assistant',
      content: 'Confirm below.',
      meta: {
        actions: [
          card('a1', 'pending', 'set_up_job_hunter', { query: 'data engineer', hour: '7' }),
          card('a2', 'failed', 'run_routine', { name: 'Morning' }),
        ],
      },
    },
  ]
  renderWithApp(<ChatPage />, { at: '/chat/c1', path: '/chat/:conversationId' })
  const [hunter, run] = screen.getAllByRole('region', { name: /^Suggested action/ })
  expect(hunter).toHaveTextContent('Every day at 07:00 · fit ≥ 60/100')
  expect(hunter).toHaveTextContent('Searchdata engineer') // the details list, hour left to the line above
  expect(within(hunter).getByRole('button', { name: 'Confirm' })).toBeInTheDocument()
  expect(run).toHaveTextContent('No flow has that name.')
  expect(within(run).queryByRole('button')).toBeNull()
  mocks.messages = undefined
})

test('an inbox message renders as a row with its link, not a reply', () => {
  mocks.profile = { data: { id: 'p' }, isPending: false }
  mocks.messages = [
    {
      id: 'm1',
      role: 'assistant',
      content: 'Morning hunt finished: 3 new matches.',
      meta: { inbox: { kind: 'run_done', link: '/automations/runs/r1' } },
    },
  ]
  renderWithApp(<ChatPage />, { at: '/chat/c1', path: '/chat/:conversationId' })
  expect(screen.getByText('Morning hunt finished: 3 new matches.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/automations/runs/r1')
  expect(screen.queryByRole('button', { name: 'Copy answer' })).toBeNull()
  mocks.messages = undefined
})
