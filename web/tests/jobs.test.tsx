import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { JobsPage } from '@/features/job-search/JobsPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PATCH: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const job = {
  id: 'j1',
  source: 'manual',
  created_at: '2026-10-04T10:00:00Z',
  data: { title: 'Python Dev', company: { name: 'Acme' }, badges: {} },
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
  mocks.POST.mockResolvedValue({ data: job, response: { status: 201 } })
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
      : { data: [job, { ...job, id: 'j2' }], response: { status: 201 } },
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
    dataTransfer: { files: [new File(['d'], 'sheet.xlsx'), new File(['e'], 'e.pdf')] },
  })
  expect(screen.getByText(/Skipped sheet\.xlsx/)).toBeInTheDocument()
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

test('the same text pasted twice says it is already there; a job is deleted after a confirmation', async () => {
  const user = userEvent.setup()
  const listed = { ...job, data: { ...job.data, source_meta: { apply_url: null } } }
  mocks.GET.mockImplementation(async (url: string) =>
    url === '/api/v1/jobs' ? { data: [listed] } : { data: [] },
  )
  mocks.POST.mockResolvedValue({ data: listed, response: { status: 200 } })
  mocks.DELETE.mockResolvedValue({ data: undefined })
  // The job list holds links, so this test needs a router.
  renderWithApp(<JobsPage />, { at: '/jobs', path: '/jobs' })

  await user.type(await screen.findByLabelText('Job description text'), 'We hire a Python dev')
  await user.click(screen.getByRole('button', { name: 'Add job' }))
  expect(
    await screen.findByText('Already in your jobs: nothing new was analysed.'),
  ).toBeInTheDocument()

  await user.click(await screen.findByRole('button', { name: 'Delete Python Dev' }))
  expect(mocks.DELETE).not.toHaveBeenCalled()
  expect(screen.getByText(/Your letters and tracked applications stay/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Confirm delete' }))
  await waitFor(() =>
    expect(mocks.DELETE).toHaveBeenCalledWith('/api/v1/jobs/{job_id}', {
      params: { path: { job_id: 'j1' } },
    }),
  )
})

test('a job missing its company shows a placeholder and a form that PATCHes only what was filled', async () => {
  const user = userEvent.setup()
  const listed = {
    ...job,
    data: { ...job.data, company: { name: '' }, source_meta: { apply_url: null } },
  }
  mocks.GET.mockImplementation(async (url: string) =>
    url === '/api/v1/jobs' ? { data: [listed] } : { data: [] },
  )
  mocks.PATCH.mockResolvedValue({ data: listed })
  renderWithApp(<JobsPage />, { at: '/jobs', path: '/jobs' })

  expect(await screen.findByText('Company not set')).toBeInTheDocument()
  expect(screen.getByText(/Missing: company \/ address/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Add' }))
  await user.type(screen.getByLabelText('Company'), 'Acme')
  await user.type(screen.getByLabelText('Location'), 'Lyon')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() =>
    expect(mocks.PATCH).toHaveBeenCalledWith('/api/v1/jobs/{job_id}', {
      params: { path: { job_id: 'j1' } },
      body: { company_name: 'Acme', company_address: '', location: 'Lyon' },
    }),
  )
})
