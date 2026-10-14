import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { JobsPage } from '@/features/job-search/JobsPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const job = {
  id: 'j1',
  source: 'manual',
  created_at: '2026-10-04T10:00:00Z',
  data: { title: 'Python Dev', company: { name: 'Acme' } },
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.GET.mockImplementation(async (url: string) =>
    url === '/api/v1/jobs/search'
      ? {
          data: {
            meta: {},
            results: [{ id: 'ft1', title: 'Dev Python', company: 'Beta', location: 'Paris' }],
          },
        }
      : { data: [] },
  )
  mocks.POST.mockResolvedValue({ data: job })
})

const renderPage = () => renderWithApp(<JobsPage />)

test('empty inbox; manual entry validates, then adds a manual job', async () => {
  const user = userEvent.setup()
  renderPage()
  expect(await screen.findByText('No jobs yet')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Add job' }))
  expect(await screen.findByText('Paste the job description first.')).toBeInTheDocument()
  expect(mocks.POST).not.toHaveBeenCalled()

  await user.type(screen.getByLabelText('Job description text'), 'We hire a Python dev')
  await user.click(screen.getByRole('button', { name: 'Add job' }))
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/jobs', {
      body: { source: 'manual', text: 'We hire a Python dev' },
    }),
  )
  expect(await screen.findByText('Job added: Python Dev')).toBeInTheDocument()
})

test('search results can be added by external id; a search error shows message + request id', async () => {
  const user = userEvent.setup()
  renderPage()
  await user.type(screen.getByLabelText('Keywords'), 'python')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  expect(await screen.findByText('Dev Python')).toBeInTheDocument()
  expect(mocks.GET).toHaveBeenCalledWith('/api/v1/jobs/search', {
    params: { query: expect.objectContaining({ query: 'python' }) },
  })
  await user.click(screen.getByRole('button', { name: 'Add Dev Python' }))
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/jobs', {
      body: { source: 'france_travail', external_id: 'ft1' },
    }),
  )

  mocks.GET.mockImplementation(async (url: string) =>
    url === '/api/v1/jobs/search'
      ? { error: { detail: 'Job search is not configured.', request_id: 'rq9' } }
      : { data: [] },
  )
  await user.click(screen.getByRole('button', { name: /All France/ }))
  await user.click(screen.getByRole('checkbox', { name: 'Paris (75)' }))
  await user.click(screen.getByRole('button', { name: 'Search' }))
  expect(await screen.findByText(/not configured\. \(request id: rq9\)/)).toBeInTheDocument()
})

test('several files are uploaded, then analysed together in one call', async () => {
  const user = userEvent.setup()
  mocks.POST.mockImplementation(async (url: string, opts: { body: { file?: File } }) =>
    url === '/api/v1/documents'
      ? { data: { document_id: `id-${opts.body.file?.name}` } }
      : { data: [job, { ...job, id: 'j2' }] },
  )
  renderPage()
  const picker = screen.getByLabelText('Job description files')
  const a = new File(['%PDF'], 'a.pdf', { type: 'application/pdf' })
  const b = new File(['x'], 'b.png', { type: 'image/png' })
  const c = new File(['y'], 'c.png', { type: 'image/png' })
  await user.upload(picker, [a]) // a second pick ADDS to the batch, it does not replace it
  await user.upload(picker, [a, b, c]) // a is already there: not added twice
  // A drop bypasses the dialog's `accept` filter: unsupported types are skipped in code.
  fireEvent.drop(picker.parentElement!, {
    dataTransfer: { files: [new File(['d'], 'notes.docx'), new File(['e'], 'e.pdf')] },
  })
  expect(screen.getByText(/Skipped notes\.docx/)).toBeInTheDocument()
  expect(screen.getByText('e.pdf')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Remove e.pdf' }))
  await user.click(screen.getByRole('button', { name: 'Remove c.png' }))
  expect(screen.queryByText('c.png')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Upload and add' }))
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/jobs/from-file', {
      body: { source: 'file', document_ids: ['id-a.pdf', 'id-b.png'] },
    }),
  )
  expect(mocks.POST.mock.calls.filter(([u]) => u === '/api/v1/jobs/from-file')).toHaveLength(1)
  expect(await screen.findByText('2 jobs added')).toBeInTheDocument()
})
