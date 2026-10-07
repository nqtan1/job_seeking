import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FitPage } from '@/features/fit/FitPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const JOB_DATA = {
  title: 'Python Dev',
  company: { name: 'Acme' },
  badges: { contract_type: 'CDI', location: 'Paris', salary: '50k' },
  profile: { technical_skills: ['Python'], nice_to_have: [] },
  tech_stack: ['FastAPI'],
  missions: ['Build APIs'],
  job_description_text: 'We build APIs.\nJoin us in Paris.',
}

const fit = {
  id: 'f1',
  score: 72.4,
  data: {
    recommendation: 'good_fit',
    summary: 'Solid match.',
    strengths: ['Python'],
    gaps: ['Kubernetes'],
    key_missing_requirements: [],
    constructive_feedback: 'Learn k8s.',
  },
}

const renderPage = () =>
  renderWithApp(<FitPage />, { at: '/jobs/j1/fit', path: '/jobs/:jobId/fit' })

beforeEach(() => {
  vi.clearAllMocks()
  mocks.GET.mockImplementation(
    async (url: string) =>
      url === '/api/v1/jobs/{job_id}'
        ? { data: { id: 'j1', source: 'manual', external_id: null, data: JOB_DATA } }
        : { data: [] }, // fit analyses, letters, applications
  )
})

test('no analysis yet → run it for the chosen company type → report is shown; errors are safe', async () => {
  const user = userEvent.setup()
  mocks.POST.mockResolvedValueOnce({
    error: { detail: 'The AI provider is unavailable.', request_id: 'rq2' },
  })
  renderPage()
  expect(await screen.findByText('No analysis yet')).toBeInTheDocument()

  await user.selectOptions(screen.getByLabelText('Company type'), 'startup')
  await user.click(screen.getByRole('button', { name: 'Analyse my fit' }))
  expect(await screen.findByText(/unavailable\. \(request id: rq2\)/)).toBeInTheDocument()

  mocks.POST.mockResolvedValueOnce({ data: fit })
  await user.click(screen.getByRole('button', { name: 'Analyse my fit' }))
  expect(await screen.findByRole('img', { name: 'Score 72 out of 100' })).toBeInTheDocument()
  expect(screen.getByText('Kubernetes')).toBeInTheDocument()
  // the offer itself sits next to the analysis
  expect(screen.getByText('Job description')).toBeInTheDocument()
  expect(screen.getByText('Build APIs')).toBeInTheDocument()
  expect(screen.getByText(/Join us in Paris/)).toBeInTheDocument()
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenLastCalledWith('/api/v1/fit-analyses', {
      body: { job_id: 'j1', company_type: 'startup' },
    }),
  )
})

test('after the report, "I applied" puts the job in the tracker as applied', async () => {
  const user = userEvent.setup()
  mocks.GET.mockImplementation(async (url: string) =>
    url === '/api/v1/jobs/{job_id}'
      ? {
          data: {
            id: 'j1',
            source: 'manual',
            external_id: null,
            data: JOB_DATA,
          },
        }
      : { data: url === '/api/v1/fit-analyses' ? [{ ...fit, job_id: 'j1' }] : [] },
  )
  mocks.POST.mockResolvedValue({ data: { id: 'a1' } })
  renderPage()

  await user.click(await screen.findByRole('button', { name: 'I applied' }))

  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/applications', {
      body: { job_id: 'j1', source: 'other', status: 'applied' },
    }),
  )
})
