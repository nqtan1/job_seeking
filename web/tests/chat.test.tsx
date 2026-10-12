import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatPage } from '@/features/coach/ChatPage'
import { createConversation, streamMessage } from '@/features/coach/api'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({
  profile: { data: { id: 'p' } as unknown, isPending: false },
  finish: () => {},
}))
vi.mock('@/features/candidate/api', () => ({ useProfile: () => mocks.profile }))
vi.mock('@/features/job-search/api', () => ({
  useJobs: () => ({
    data: [{ id: 'j1', data: { title: 'AI Engineer', company: { name: 'Acme' } } }],
  }),
}))
vi.mock('@/features/coach/api', () => ({
  useConversation: () => ({ data: undefined }),
  useDeleteConversation: () => ({ mutate: vi.fn(), isPending: false }),
  useSetFocus: () => ({ mutate: vi.fn(), isPending: false }),
  useMessages: () => ({ data: undefined, isLoading: false, isPending: true }),
  createConversation: vi.fn(async () => ({ id: 'c1' })),
  regenerateReply: vi.fn(),
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
      await new Promise<void>((resolve) => (mocks.finish = resolve)) // keep the stream open
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

test('"Discuss this job" opens a chat focused on that job', async () => {
  mocks.profile = { data: { id: 'p' }, isPending: false }
  renderWithApp(<ChatPage />, { at: '/?job=j1', path: '/' })
  expect(await screen.findByText('AI Engineer')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Review my CV' }))
  expect(createConversation).toHaveBeenCalledWith('j1')
  mocks.finish()
})
