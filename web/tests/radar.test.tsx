import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RadarPage } from '@/features/radar/RadarPage'
import { renderWithApp } from './utils'

const mocks = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PATCH: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const search = {
  id: 's1',
  name: 'Python Paris',
  query: 'python',
  department: '75',
  contract_type: null,
  min_score: 70,
  daily_limit: 5,
  enabled: true,
  last_run_at: null,
  created_at: '2026-10-06T08:00:00Z',
}
const match = {
  id: 'r1',
  search_id: 's1',
  search_name: 'Python Paris',
  job_id: 'j1',
  score: 84,
  status: 'new',
  found_at: new Date().toISOString(),
  title: 'Dev Python',
  company: 'Acme',
  highlights: {
    strengths: ['FastAPI experience', 'Postgres'],
    gaps: [],
    missing: ['Kubernetes'],
    summary: null,
  },
  application_status: null,
}
const rejected = {
  ...match,
  id: 'r2',
  job_id: null,
  score: 41,
  status: 'skipped',
  title: 'Java Dev',
  company: 'Corp',
  highlights: { strengths: [], gaps: [], missing: ['Spring'], summary: null },
}
const status = {
  new_matches: 1,
  searches: 1,
  daily_searches: 1,
  running: false,
  last_run: {
    id: 'u1',
    search_id: 's1',
    started_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    status: 'ok',
    stop_reason: 'limit',
    found: 25,
    added: 5,
    scored: 5,
    shortlisted: 2,
  },
  next_run_at: new Date(Date.now() + 86_400_000).toISOString(),
}
const insights = {
  days: 30,
  funnel: { scored: 24, shortlisted: 6, approved: 3, applied: 2, interviews: 1 },
  average_score: 66.4,
  most_missing: [{ text: 'kubernetes', count: 4 }],
}

let data: Record<string, unknown>
beforeEach(() => {
  vi.clearAllMocks()
  data = {
    searches: [search],
    new: [match],
    approved: [],
    skipped: [rejected],
    runs: [status.last_run],
    status,
    insights,
    usage: { used: 12, quota: 50, radar_stops_at: 35 },
    profile: { data: { experiences: [] } },
  }
  mocks.GET.mockImplementation(
    async (url: string, opts?: { params?: { query?: { status?: string } } }) => {
      if (url.endsWith('/results'))
        return { data: data[opts?.params?.query?.status ?? 'new'], response: { status: 200 } }
      const key = url.split('/').pop() as string
      return { data: data[key] ?? [], response: { status: 200 } }
    },
  )
})

const renderPage = () => renderWithApp(<RadarPage />, { at: '/radar', path: '/radar' })

test('the user sees the radar working: status, last and next run, new matches and the reasons', async () => {
  renderPage()

  const strip = await screen.findByRole('region', { name: 'Radar status' })
  expect(within(strip).getByText('Idle')).toBeInTheDocument()
  expect(within(strip).getByText(/looked at 5 new offers, kept 2/)).toBeInTheDocument()
  expect(within(strip).getByText(/Next run tomorrow/)).toBeInTheDocument()
  expect(within(strip).getByText('1 new match')).toBeInTheDocument()
  const card = (await screen.findByText('Dev Python')).closest('li') as HTMLElement
  expect(within(card).getByText('Fit 84%')).toBeInTheDocument()
  expect(within(card).getByText('FastAPI experience')).toBeInTheDocument() // why it fits
  expect(within(card).getByText('Kubernetes')).toBeInTheDocument() // what to watch
  expect(screen.getByText(/AI use today: 12 of 50/)).toBeInTheDocument()
})

test('insights show the funnel and what is missing most often', async () => {
  renderPage()

  const panel = await screen.findByRole('region', { name: 'Your last 30 days' })
  expect(within(panel).getByText('24')).toBeInTheDocument()
  expect(within(panel).getByText(/Interviews/)).toBeInTheDocument()
  expect(within(panel).getByText('kubernetes ×4')).toBeInTheDocument()
})

test('rejected jobs are visible, with why, and can be reviewed anyway', async () => {
  const user = userEvent.setup()
  mocks.POST.mockResolvedValue({ data: { job_id: 'j9' } })
  renderPage()

  await user.click(await screen.findByText(/Checked but not shortlisted \(1\)/))
  expect(screen.getByText(/missing: Spring/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Review Java Dev anyway' }))

  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/radar/results/{result_id}/keep', {
      params: { path: { result_id: 'r2' } },
    }),
  )
})

test('dismissing a match calls the API', async () => {
  const user = userEvent.setup()
  mocks.POST.mockResolvedValue({ data: undefined })
  renderPage()

  await user.click(await screen.findByRole('button', { name: 'Dismiss Dev Python' }))

  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/radar/results/{result_id}/dismiss', {
      params: { path: { result_id: 'r1' } },
    }),
  )
})

test('a first-time user gets a one-click radar from their CV and a how-it-works', async () => {
  const user = userEvent.setup()
  data.searches = []
  data.new = []
  data.skipped = []
  data.runs = []
  data.status = {
    ...status,
    searches: 0,
    daily_searches: 0,
    new_matches: 0,
    last_run: null,
    next_run_at: null,
  }
  data.insights = { ...insights, funnel: { ...insights.funnel, scored: 0 } }
  data.profile = { data: { experiences: [{ job_title: 'Data Engineer' }] } }
  mocks.POST.mockResolvedValue({ data: search })
  renderPage()

  expect(await screen.findByText('No radar yet')).toBeInTheDocument()
  expect(screen.getByText(/It never applies for you and never contacts a company/)).toBeVisible()
  await user.click(await screen.findByRole('button', { name: 'Start this radar' }))

  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/radar/searches', {
      body: {
        name: 'Data Engineer',
        query: 'Data Engineer',
        min_score: 70,
        daily_limit: 5,
        enabled: true,
      },
    }),
  )
})

test('an existing radar can be edited and only the edited radar changes', async () => {
  const user = userEvent.setup()
  mocks.PATCH.mockResolvedValue({ data: search })
  renderPage()

  await user.click(await screen.findByRole('button', { name: 'Edit Python Paris' }))
  const keywords = screen.getByLabelText('Keywords')
  expect(keywords).toHaveValue('python') // filled with what is there now
  await user.clear(keywords)
  await user.type(keywords, 'data engineer')
  await user.clear(screen.getByLabelText('Minimum fit (%)'))
  await user.type(screen.getByLabelText('Minimum fit (%)'), '60')
  await user.click(screen.getByRole('button', { name: 'Save changes' }))

  await waitFor(() =>
    expect(mocks.PATCH).toHaveBeenCalledWith('/api/v1/radar/searches/{search_id}', {
      params: { path: { search_id: 's1' } },
      body: {
        name: 'Python Paris',
        query: 'data engineer',
        department: '75',
        contract_type: null,
        min_score: 60,
        daily_limit: 5,
      },
    }),
  )
})

test('a new radar takes keyword alternatives, several places and a list of contracts', async () => {
  const user = userEvent.setup()
  data.searches = []
  data.new = []
  data.skipped = []
  mocks.POST.mockResolvedValue({ data: search })
  renderPage()

  await user.click(await screen.findByRole('button', { name: 'New radar' }))
  await user.type(screen.getByLabelText('Name'), 'AI roles')
  await user.type(screen.getByLabelText('Keywords'), 'IA Engineer, ML Engineer')
  await user.click(screen.getByRole('button', { name: /All France/ }))
  await user.click(screen.getByRole('checkbox', { name: 'Paris (75)' }))
  await user.click(screen.getByRole('checkbox', { name: 'Lyon · Rhône (69)' }))
  await user.click(screen.getByRole('button', { name: 'CDI' }))
  await user.click(screen.getByRole('button', { name: 'CDD' }))
  await user.click(screen.getByRole('button', { name: 'Add radar' }))

  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/radar/searches', {
      body: {
        name: 'AI roles',
        query: 'IA Engineer, ML Engineer',
        department: '75,69',
        contract_type: 'CDI,CDD',
        min_score: 70,
        daily_limit: 5,
        enabled: true,
      },
    }),
  )
})

test('an interrupted run is explained and can be retried at once', async () => {
  const user = userEvent.setup()
  data.status = {
    ...status,
    interrupted: true,
    interrupted_reason: 'ai_unavailable',
    last_run: {
      ...status.last_run,
      status: 'partial',
      stop_reason: 'ai_unavailable',
      found: 2,
      scored: 0,
      shortlisted: 0,
    },
  }
  mocks.POST.mockResolvedValue({ data: { task_id: 't1', status_url: '/x' } })
  renderPage()

  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('The last run was interrupted (the AI was unavailable)')
  expect(alert).toHaveTextContent('found 2 offers and scored 0. Nothing was lost')
  await user.click(within(alert).getByRole('button', { name: 'Retry now' }))

  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith('/api/v1/radar/searches/{search_id}/run', {
      params: { path: { search_id: 's1' } },
    }),
  )
})
