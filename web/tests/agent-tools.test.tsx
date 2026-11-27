import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AgentToolsPage } from '@/features/helpers/AgentToolsPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))
vi.mock('@/features/settings/api', () => ({ useMe: () => ({ data: { helpers_enabled: true } }) }))

const tool = (id: string, over: object = {}) => ({
  id,
  pack: 'career',
  inputs: [],
  outputs: ['text'],
  effect: 'read',
  ai_uses: 0,
  daily_cap: null,
  needs_job: false,
  chat: true,
  page: null,
  mcp: true,
  ...over,
})

test('Studio › Tools lists what agents can use, its health, and runs one for real in a side panel', async () => {
  const save = tool('save_note', {
    inputs: [
      { name: 'title', required: true },
      { name: 'body', required: true },
      { name: 'source_url', required: false },
    ],
    outputs: ['note_id'],
    effect: 'write',
    daily_cap: 100,
  })
  mocks.GET.mockImplementation(async (url: string) => ({
    data:
      url === '/api/v1/tools'
        ? [save, tool('profile_read'), tool('send_email', { mcp: false })]
        : { remote: true, ok: true, served: ['save_note'], latency_ms: 42 },
  }))
  mocks.POST.mockResolvedValue({
    data: { outputs: { note_id: 'n1' }, latency_ms: 120, remote: true },
  })
  const user = userEvent.setup()
  renderWithApp(<AgentToolsPage />, { at: '/agent-tools', path: '/agent-tools' })

  // only agent tools; plain names; a tool the running service lacks says so
  expect(await screen.findByText('Save a note')).toBeInTheDocument()
  expect(screen.queryByText(/send an email/i)).not.toBeInTheDocument()
  expect(await screen.findByText('Online · 42 ms')).toBeInTheDocument()
  expect(screen.getByText('Not served')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Try Save a note' }))
  const panel = screen.getByRole('dialog', { name: 'Save a note' })
  // what it needs, in words, with what it gives back before any run
  expect(within(panel).getByText('Changes your data')).toBeInTheDocument()
  expect(within(panel).getByText(/really runs/)).toBeInTheDocument()
  expect(within(panel).getByText('{{note_id}}')).toBeInTheDocument()
  const run = within(panel).getByRole('button', { name: 'Run' })
  expect(run).toBeDisabled() // a disabled button says why
  expect(within(panel).getByText('Fill in the text above to run it.')).toBeInTheDocument()

  await user.type(within(panel).getByLabelText('Note title'), 'Lyon offers')
  await user.type(within(panel).getByLabelText('Note text'), 'Three to read.')
  await user.click(run)
  await waitFor(() => expect(mocks.POST).toHaveBeenCalled())
  expect(mocks.POST.mock.calls[0]?.[1]).toEqual({
    params: { path: { tool_id: 'save_note' } },
    body: { inputs: { title: 'Lyon offers', body: 'Three to read.' }, job_id: null }, // blanks stay out
  })
  expect(await within(panel).findByText('120 ms on the tools service')).toBeInTheDocument()
  expect(within(panel).getByText('n1')).toBeInTheDocument()
})
