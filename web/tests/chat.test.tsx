import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatPage } from '@/features/coach/ChatPage'
import { streamMessage } from '@/features/coach/api'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({
  profile: { data: { id: 'p' } as unknown, isPending: false },
  finish: () => {},
}))
vi.mock('@/features/candidate/api', () => ({ useProfile: () => mocks.profile }))
vi.mock('@/features/coach/api', () => ({
  useMessages: () => ({ data: undefined, isLoading: false, isPending: true }),
  createConversation: vi.fn(async () => ({ id: 'c1' })),
  streamMessage: vi.fn(async (_id: string, _text: string, onToken: (t: string) => void) => {
    onToken('Hello ')
    onToken('there')
    await new Promise<void>((resolve) => (mocks.finish = resolve)) // keep the stream open
  }),
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
  expect(await screen.findByText('Hello there')).toBeInTheDocument()
  expect(streamMessage).toHaveBeenCalledWith(
    'c1',
    expect.stringContaining('Review my CV'),
    expect.any(Function),
    expect.any(AbortSignal),
  )
  mocks.finish()
})
