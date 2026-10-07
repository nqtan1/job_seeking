import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TrackerPage } from '@/features/tracker/TrackerPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PATCH: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const app = {
  id: 'a1',
  company_name: 'Acme',
  job_title: 'Dev',
  source: 'linkedin',
  status: 'applied',
  next_statuses: ['interview', 'rejected'],
  notes: null,
}

let apps: unknown[]
beforeEach(() => {
  vi.clearAllMocks()
  apps = []
  mocks.GET.mockImplementation(async (url: string) =>
    url.endsWith('/events')
      ? {
          data: [
            {
              id: 'e1',
              from_status: null,
              to_status: 'to_apply',
              at: '2026-10-01T10:00:00Z',
              note: null,
            },
            {
              id: 'e2',
              from_status: 'to_apply',
              to_status: 'applied',
              at: '2026-10-02T10:00:00Z',
              note: 'sent CV',
            },
          ],
        }
      : { data: apps },
  )
})

const renderPage = () => renderWithApp(<TrackerPage />)

test('empty board → add an application (company required) → POST with the chosen status', async () => {
  const user = userEvent.setup()
  mocks.POST.mockResolvedValue({ data: app })
  renderPage()
  expect(await screen.findByText(/No applications yet/)).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Add application' }))
  expect(mocks.POST).not.toHaveBeenCalled()
  await user.type(screen.getByLabelText('Company'), 'Acme')
  await user.selectOptions(screen.getByLabelText('Status'), 'applied')
  await user.click(screen.getByRole('button', { name: 'Add application' }))
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/applications', {
      body: expect.objectContaining({ company_name: 'Acme', status: 'applied', source: 'other' }),
    }),
  )
})

test('card sits in its column, only offers allowed moves, shows the timeline, deletes after confirmation', async () => {
  const user = userEvent.setup()
  apps = [app]
  mocks.POST.mockResolvedValue({ data: { ...app, status: 'interview' } })
  mocks.DELETE.mockResolvedValue({})
  renderPage()
  const column = await screen.findByRole('region', { name: 'Applied' })
  expect(within(column).getByText('Dev — Acme')).toBeInTheDocument()

  const move = screen.getByLabelText('Move Dev — Acme')
  expect(
    within(move)
      .getAllByRole('option')
      .map((o) => o.textContent),
  ).toEqual(['Move to…', 'Interview', 'Rejected'])
  await user.selectOptions(move, 'interview')
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/applications/{application_id}/status', {
      params: { path: { application_id: 'a1' } },
      body: { status: 'interview' },
    }),
  )

  await user.click(screen.getByRole('button', { name: 'Timeline' }))
  expect(await screen.findByText(/sent CV/)).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Delete Dev — Acme' }))
  expect(mocks.DELETE).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Confirm delete' }))
  await waitFor(() => expect(mocks.DELETE).toHaveBeenCalled())
})

test('Details: contact, interview date and notes are saved with one PATCH', async () => {
  const user = userEvent.setup()
  apps = [{ ...app, contact: null, interview_at: null }]
  mocks.PATCH.mockResolvedValue({ data: app })
  renderPage()

  await user.click(await screen.findByRole('button', { name: 'Details' }))
  await user.type(screen.getByLabelText('Contact'), 'Marie, marie@acme.test')
  await user.type(document.getElementById('notes-a1') as HTMLElement, 'Bring portfolio')
  await user.click(screen.getByRole('button', { name: 'Save' }))

  await waitFor(() =>
    expect(mocks.PATCH).toHaveBeenCalledWith('/api/v1/applications/{application_id}', {
      params: { path: { application_id: 'a1' } },
      body: { notes: 'Bring portfolio', contact: 'Marie, marie@acme.test', interview_at: null },
    }),
  )
})
