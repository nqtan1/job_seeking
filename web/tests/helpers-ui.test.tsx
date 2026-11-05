import '@/features/helpers/lib'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { RouterProvider, createMemoryRouter } from 'react-router'
import { HelperEditor } from '@/features/helpers/HelperEditor'
import { AutomationsPage } from '@/features/helpers/AutomationsPage'
import { HelpersPage } from '@/features/helpers/HelpersPage'
import { RecentRuns } from '@/features/helpers/RunParts'
import { RunPage } from '@/features/helpers/RunPage'
import { FlowEditor } from '@/features/helpers/FlowEditor'
import { NodeInspector, ValidationPanel } from '@/features/helpers/FlowPanels'
import { emptyGraph, resultLast, typeKey } from '@/features/helpers/graph'

const mocks = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PATCH: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/lib/api/client', () => ({ api: mocks }))
vi.mock('@/features/helpers/Canvas', () => ({ default: () => <div>canvas</div> })) // no layout in jsdom

const AVATAR = { seed: 'a1', body: 0, palette: 0, eyes: 0, accessory: 0 }
const SPEC = {
  role: 'custom',
  instructions: 'Write a polite follow-up.',
  model_tier: 'fast',
  inputs: [{ name: 'notes', label: 'Notes', required: true }],
  context_sources: [],
  output: { kind: 'text', fields: [] },
}
const AGENT = {
  id: 'a1',
  name: 'Mira',
  description: 'Follow-ups',
  avatar: AVATAR,
  current_version: 3,
  archived: false,
  version_id: 'v3',
  spec: SPEC,
  created_at: '2026-11-01T10:00:00Z',
  updated_at: '2026-11-01T10:00:00Z',
}

function open(ui: ReactElement, path: string, at: string) {
  const router = createMemoryRouter([{ path, element: ui }], { initialEntries: [at] })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mocks.GET.mockImplementation(async (url: string) => {
    if (url === '/api/v1/agents/{agent_id}') return { data: AGENT }
    if (url === '/api/v1/radar/usage') return { data: { used: 10, quota: 50, radar_stops_at: 40 } }
    return { data: [] }
  })
})

test('editing a helper: a version is saved on the version it started from, and a stale save never overwrites', async () => {
  const user = userEvent.setup()
  open(<HelperEditor />, '/helpers/:agentId', '/helpers/a1')
  const box = await screen.findByLabelText('Instructions')
  const save = screen.getByRole('button', { name: /Save version/ })
  expect(save).toBeDisabled() // nothing changed yet

  await user.clear(box)
  await user.type(box, 'Shorter.')
  expect(screen.getByText('Unsaved changes')).toBeInTheDocument()
  mocks.POST.mockResolvedValueOnce({ error: { status: 409, code: 'conflict', detail: 'changed' } })
  await user.click(save)
  await waitFor(() => expect(mocks.POST).toHaveBeenCalled())
  const [url, init] = mocks.POST.mock.calls[0]
  expect(url).toBe('/api/v1/agents/{agent_id}/versions')
  expect(init.body.based_on).toBe(3)
  expect(init.body.spec.instructions).toBe('Shorter.')
  // the edit is still there, not lost, and the conflict is explained instead of a silent overwrite
  expect(await screen.findByText(/changed somewhere else/)).toBeInTheDocument()
  expect(box).toHaveValue('Shorter.')
})

test('trying a helper needs its required input and shows the answer with its cost', async () => {
  const user = userEvent.setup()
  open(<HelperEditor />, '/helpers/:agentId', '/helpers/a1')
  const run = await screen.findByRole('button', { name: 'Run' })
  expect(run).toBeDisabled() // "Notes" is required
  expect(await screen.findByText('40 AI uses left today')).toBeInTheDocument()

  mocks.POST.mockResolvedValueOnce({
    data: { result: { text: 'Dear team…' }, model: 'm1', latency_ms: 1200 },
  })
  await user.type(screen.getByLabelText('Notes', { selector: '#try-notes' }), 'Applied last week')
  await user.click(run)
  expect(await screen.findByText('Dear team…')).toBeInTheDocument()
  expect(screen.getByText('m1 · 1.2 s')).toBeInTheDocument()
  expect(mocks.POST.mock.calls[0][1].body.inputs).toEqual({ notes: 'Applied last week' })
})

test('the gallery starts a helper from a template', async () => {
  const user = userEvent.setup()
  mocks.POST.mockResolvedValueOnce({ data: { ...AGENT, id: 'new1' } })
  open(<HelpersPage />, '/helpers', '/helpers')
  expect(await screen.findByText('No helper yet')).toBeInTheDocument()
  await user.click(screen.getAllByRole('button', { name: 'Use this template' })[0])
  await waitFor(() => expect(mocks.POST).toHaveBeenCalled())
  expect(mocks.POST.mock.calls[0][1].body.name).toBe('Follow-up writer')
  expect(mocks.POST.mock.calls[0][1].body.spec.instructions).toContain('follow-up')
})

test('a failed run explains itself in plain words and can be resumed; skipped steps say why', async () => {
  const user = userEvent.setup()
  const N = { i: 'n-input', a: 'n-agent', o: 'n-output' }
  const graph = {
    schema_version: 1,
    nodes: [
      { type: 'input', id: N.i, fields: [{ name: 'n', label: 'N' }] },
      { type: 'agent', id: N.a, agent_id: 'a1', agent_version_id: 'v3' },
      { type: 'output', id: N.o, fields: [{ name: 'r', label: 'R' }] },
    ],
    edges: [],
  }
  const run = {
    id: 'r1',
    flow_id: 'f1',
    flow_version_id: 'fv1',
    status: 'failed',
    error_code: 'quota_exceeded',
    created_at: '2026-11-02T10:00:00Z',
    finished_at: null,
    started_at: null,
    inputs: {},
    job_id: null,
    result: null,
    handoffs: [],
    steps: [
      {
        node_id: N.i,
        position: 0,
        status: 'done',
        output: { n: 'hi' },
        error_code: null,
        model: null,
        latency_ms: null,
        started_at: null,
        finished_at: null,
      },
      {
        node_id: N.a,
        position: 1,
        status: 'failed',
        output: null,
        error_code: 'quota_exceeded',
        model: null,
        latency_ms: null,
        started_at: null,
        finished_at: null,
      },
      {
        node_id: N.o,
        position: 2,
        status: 'skipped',
        output: null,
        error_code: null,
        model: null,
        latency_ms: null,
        started_at: null,
        finished_at: null,
      },
    ],
  }
  mocks.GET.mockImplementation(async (url: string) => {
    if (url === '/api/v1/flow-runs/{run_id}') return { data: run }
    if (url === '/api/v1/flows/{flow_id}/versions')
      return { data: [{ id: 'fv1', flow_id: 'f1', version: 1, graph, note: '', created_at: '' }] }
    if (url === '/api/v1/agents') return { data: [AGENT] }
    if (url === '/api/v1/agents/{agent_id}/versions')
      return {
        data: [{ id: 'v3', agent_id: 'a1', version: 3, spec: SPEC, note: '', created_at: '' }],
      }
    return { data: [] }
  })
  mocks.POST.mockResolvedValueOnce({ data: { ...run, status: 'queued' } })
  open(<RunPage />, '/automations/runs/:runId', '/automations/runs/r1')

  expect(await screen.findAllByText(/reached today’s AI limit/)).not.toHaveLength(0)
  expect(screen.queryByText('quota_exceeded')).not.toBeInTheDocument() // never the raw code
  expect(screen.getByText(/Skipped: the condition/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Resume from the failed step' }))
  await waitFor(() => expect(mocks.POST).toHaveBeenCalled())
  expect(mocks.POST.mock.calls[0][0]).toBe('/api/v1/flow-runs/{run_id}/resume')
})

test('typing choice options with commas keeps what you type, and the draft sends only declared inputs', async () => {
  const user = userEvent.setup()
  mocks.GET.mockImplementation(async (url: string) =>
    url === '/api/v1/agents/{agent_id}'
      ? {
          data: {
            ...AGENT,
            spec: {
              ...SPEC,
              output: {
                kind: 'fields',
                fields: [{ name: 'risk', type: 'choice', options: ['low', 'high'] }],
              },
            },
          },
        }
      : url === '/api/v1/radar/usage'
        ? { data: { used: 0, quota: 50, radar_stops_at: 40 } }
        : { data: [] },
  )
  open(<HelperEditor />, '/helpers/:agentId', '/helpers/a1')
  const options = await screen.findByLabelText('Options, separated by commas')
  await user.clear(options)
  await user.type(options, 'red,blue, green')
  expect(options).toHaveValue('red,blue, green') // commas survive every keystroke

  mocks.POST.mockResolvedValueOnce({
    data: { result: { risk: 'low' }, model: 'm', latency_ms: 10 },
  })
  await user.type(screen.getByLabelText('Notes', { selector: '#try-notes' }), 'x')
  await user.click(screen.getByRole('button', { name: 'Run' }))
  await waitFor(() => expect(mocks.POST).toHaveBeenCalled())
  const body = mocks.POST.mock.calls.at(-1)![1].body
  expect(Object.keys(body.inputs)).toEqual(['notes'])
  expect(body.spec.output.fields[0].options).toEqual(['red', 'blue', 'green'])
})

test('a finished run leads with its summary and the result, then the steps', async () => {
  const N = { i: 'n-input', a: 'n-agent', o: 'n-output' }
  const graph = {
    schema_version: 1,
    nodes: [
      { type: 'input', id: N.i, fields: [{ name: 'n', label: 'N' }] },
      { type: 'agent', id: N.a, agent_id: 'a1', agent_version_id: 'v3' },
      { type: 'output', id: N.o, fields: [{ name: 'r', label: 'R' }] },
    ],
    edges: [],
  }
  const step = (node_id: string, position: number, model: string | null) => ({
    node_id,
    position,
    status: 'done',
    output: { text: 'A canned helper answer.' },
    error_code: null,
    model,
    latency_ms: 1200,
    started_at: null,
    finished_at: null,
  })
  const run = {
    id: 'r2',
    flow_id: 'f1',
    flow_version_id: 'fv1',
    status: 'done',
    error_code: null,
    created_at: '2026-11-02T10:00:00Z',
    started_at: '2026-11-02T10:00:00Z',
    finished_at: '2026-11-02T10:00:04Z',
    inputs: {},
    job_id: null,
    result: { text: 'A canned helper answer.' },
    handoffs: [],
    steps: [step(N.i, 0, null), step(N.a, 1, 'm1'), step(N.o, 2, null)],
  }
  mocks.GET.mockImplementation(async (url: string) => {
    if (url === '/api/v1/flow-runs/{run_id}') return { data: run }
    if (url === '/api/v1/flows/{flow_id}/versions')
      return { data: [{ id: 'fv1', flow_id: 'f1', version: 1, graph, note: '', created_at: '' }] }
    if (url === '/api/v1/agents') return { data: [AGENT] }
    return { data: [] }
  })
  open(<RunPage />, '/automations/runs/:runId', '/automations/runs/r2')

  expect(await screen.findByText('3 of 3 steps')).toBeInTheDocument()
  expect(screen.getAllByText('Done')[0]).toBeInTheDocument() // the status badge comes first
  expect(screen.getByText('Took 4.0 s')).toBeInTheDocument()
  expect(screen.getByText('1 AI use')).toBeInTheDocument() // only the step that used a model
  expect(screen.getByRole('region', { name: 'Result' })).toHaveTextContent(
    'A canned helper answer.',
  )
  expect(screen.getAllByRole('button', { name: 'Details' })).toHaveLength(1) // start/result stay quiet
})

test('recent runs link back to their run page, newest first', async () => {
  mocks.GET.mockResolvedValue({
    data: [
      {
        id: 'r2',
        flow_id: 'f1',
        flow_version_id: 'v',
        status: 'failed',
        error_code: 'x',
        created_at: new Date().toISOString(),
        finished_at: null,
      },
      {
        id: 'r1',
        flow_id: 'f1',
        flow_version_id: 'v',
        status: 'done',
        error_code: null,
        created_at: new Date().toISOString(),
        finished_at: null,
      },
    ],
  })
  open(<RecentRuns flowId="f1" />, '/x', '/x')
  const links = await screen.findAllByRole('link')
  expect(links.map((l) => l.getAttribute('href'))).toEqual([
    '/automations/runs/r2',
    '/automations/runs/r1',
  ])
  expect(screen.getByText('Failed')).toBeInTheDocument()
})

describe('the flow editor', () => {
  const FSPEC = {
    role: 'custom',
    instructions: 'x',
    model_tier: 'fast',
    inputs: [{ name: 'notes', label: 'Notes', required: true }],
    context_sources: [],
    output: { kind: 'text', fields: [] },
  }
  const FAGENT = {
    id: 'a1',
    name: 'Mira',
    description: '',
    avatar: { seed: 'a1', body: 0, palette: 0, eyes: 0, accessory: 0 },
    current_version: 1,
    archived: false,
    version_id: 'v1',
    spec: FSPEC,
    created_at: '',
    updated_at: '',
  }
  const graph = emptyGraph('notes', 'result', ['Notes', 'Result'])
  const FLOW = {
    id: 'f1',
    name: 'My flow',
    current_version: 1,
    graph,
    issues: [],
    created_at: '',
    updated_at: '',
  }

  function renderEditor() {
    const router = createMemoryRouter([{ path: '/automations/:flowId', element: <FlowEditor /> }], {
      initialEntries: ['/automations/f1'],
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
  }

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    mocks.GET.mockImplementation(async (url: string) => {
      if (url === '/api/v1/flows/{flow_id}') return { data: FLOW }
      if (url === '/api/v1/agents') return { data: [FAGENT] }
      if (url === '/api/v1/agents/{agent_id}') return { data: FAGENT }
      if (url === '/api/v1/agents/{agent_id}/versions')
        return {
          data: [{ id: 'v1', agent_id: 'a1', version: 1, spec: FSPEC, note: '', created_at: '' }],
        }
      return { data: [] }
    })
    mocks.POST.mockResolvedValue({ data: { issues: [] } })
  })

  test('the Result step is always last in a target list, and the transform is "Clean text" to people', () => {
    const ids = graph.nodes.map((n) => n.id)
    const [start, result] = ids
    expect(resultLast(graph, [result, start, 'x'])).toEqual([start, 'x', result])
    expect(typeKey('transform')).toBe('helpers.node.transform_name')
  })

  test('the header carries save and run with an always-present save status; adding a step makes it unsaved', async () => {
    const user = userEvent.setup()
    renderEditor()
    await screen.findByRole('button', { name: /Save version/ })
    const banner = screen.getByRole('banner')
    const status = within(banner).getByRole('status')
    expect(status).toHaveTextContent('All changes saved')
    expect(within(banner).getByRole('button', { name: /Save version/ })).toBeDisabled()
    expect(within(banner).getByRole('button', { name: 'Run flow' })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: 'Steps' }))
    await user.selectOptions(await screen.findByLabelText('Add a helper…'), 'Mira')
    expect(await within(banner).findByRole('status')).toHaveTextContent('Unsaved changes')
    expect(within(banner).getByRole('button', { name: 'Run flow' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Clean text' })) // the renamed transform
    const send = screen.getAllByLabelText('Send to…')[0] // Start's list
    const labels = within(send)
      .getAllByRole('option')
      .map((o) => o.textContent)
    expect(labels.at(-1)).toBe('Result')
    expect(labels).toContain('Clean text')
  })

  test('the status card says Ready to run with the price, or lists clickable problems naming the step', async () => {
    const user = userEvent.setup()
    const onJump = vi.fn()
    const titles = new Map([['n1', 'Mira']])
    const { rerender } = render(
      <ValidationPanel titles={titles} issues={[]} aiCalls={2} onJump={onJump} />,
    )
    expect(screen.getByText('Ready to run')).toBeInTheDocument()
    expect(screen.getByText(/up to 2 AI uses/)).toBeInTheDocument()
    rerender(
      <ValidationPanel
        titles={titles}
        issues={[{ severity: 'error', code: 'cycle', node_id: 'n1', edge_id: null } as never]}
        aiCalls={2}
        onJump={onJump}
      />,
    )
    expect(screen.queryByText('Ready to run')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Mira/ }))
    expect(onJump).toHaveBeenCalledWith({ kind: 'node', id: 'n1' })
  })
})

describe('platform pages', () => {
  const RUN = (id: string, over: object = {}) => ({
    id,
    flow_id: 'f1',
    flow_version_id: 'fv1',
    trigger: 'manual',
    status: 'done',
    error_code: null,
    created_at: '2026-11-01T10:00:00Z',
    finished_at: '2026-11-01T10:01:00Z',
    flow_name: 'Follow-up',
    ...over,
  })

  test('runs: filter, load more, and run again opens the new run', async () => {
    const user = userEvent.setup()
    const first = Array.from({ length: 30 }, (_, i) =>
      RUN(
        `r${i}`,
        i === 0 ? { status: 'failed', error_code: 'ai_timeout', trigger: 'schedule' } : {},
      ),
    )
    mocks.GET.mockImplementation(
      async (
        url: string,
        init?: { params?: { query?: { status?: string; before_id?: string } } },
      ) => {
        if (url === '/api/v1/flow-runs') {
          const q = init?.params?.query
          if (q?.before_id) return { data: [RUN('last')] }
          return { data: q?.status === 'failed' ? [first[0]] : first }
        }
        return { data: [] }
      },
    )
    mocks.POST.mockResolvedValueOnce({ data: { id: 'new-run' } })
    const router = createMemoryRouter(
      [
        { path: '/automations', element: <AutomationsPage /> },
        { path: '/automations/runs/:runId', element: <div>run page</div> },
      ],
      { initialEntries: ['/automations?tab=runs'] },
    )
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    expect(
      await screen.findByText('The AI took too long. Resume to try again.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Scheduled')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Load more' }))
    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(31))
    await user.click(screen.getByRole('button', { name: 'Failed' }))
    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(1))
    await user.click(screen.getByRole('button', { name: 'Run Follow-up again' }))
    expect(await screen.findByText('run page')).toBeInTheDocument()
    expect(mocks.POST.mock.calls[0][0]).toBe('/api/v1/flow-runs/{run_id}/rerun')
  })

  test('a schedule is created with the detected time zone and the start inputs', async () => {
    const user = userEvent.setup()
    const g = {
      ...emptyGraph('notes', 'result', ['Notes', 'Result']),
    }
    const flow = {
      id: 'f1',
      name: 'My flow',
      graph: g,
      issues: [],
      max_ai_calls: 1,
      current_version: 1,
    }
    mocks.POST.mockResolvedValueOnce({ data: {} })
    const { SchedulePanel } = await import('@/features/helpers/Schedules')
    open(<SchedulePanel flow={flow as never} graph={g} specs={new Map()} />, '/', '/')
    await user.click(await screen.findByRole('button', { name: 'Add a schedule' }))
    await user.click(screen.getByLabelText('Every week'))
    await user.selectOptions(screen.getByLabelText('On which day'), '2')
    await user.type(screen.getByLabelText('Notes'), 'Acme')
    expect(screen.getByText(/It will run: Every Wednesday at 08:00/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add this schedule' }))
    await waitFor(() => expect(mocks.POST).toHaveBeenCalled())
    const [url, init] = mocks.POST.mock.calls[0]
    expect(url).toBe('/api/v1/flows/{flow_id}/schedules')
    expect(init.body).toMatchObject({
      cadence: 'weekly',
      at_time: '08:00',
      weekday: 2,
      inputs: { notes: 'Acme' },
      job_id: null,
    })
    expect(init.body.timezone).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone)
  })

  test('a ready-made automation creates its helpers, then the flow wired to them', async () => {
    const user = userEvent.setup()
    let n = 0
    mocks.POST.mockImplementation(async (url: string) =>
      url === '/api/v1/agents'
        ? { data: { ...AGENT, id: `ag${++n}`, version_id: `ve${n}` } }
        : { data: { id: 'flow9' } },
    )
    const router = createMemoryRouter(
      [
        { path: '/automations', element: <AutomationsPage /> },
        { path: '/automations/:flowId', element: <div>editor</div> },
      ],
      { initialEntries: ['/automations'] },
    )
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    const buttons = await screen.findAllByRole('button', { name: 'Create this automation' })
    await user.click(buttons[2]) // Prepare my interview: two helpers
    expect(await screen.findByText('editor')).toBeInTheDocument()
    const calls = mocks.POST.mock.calls
    expect(calls.map((c) => c[0])).toEqual(['/api/v1/agents', '/api/v1/agents', '/api/v1/flows'])
    const g = calls[2][1].body.graph
    expect(
      g.nodes
        .filter((x: { type: string }) => x.type === 'agent')
        .map((x: { agent_version_id: string }) => x.agent_version_id),
    ).toEqual(['ve1', 've2'])
    expect(g.edges).toHaveLength(4)
    expect(g.nodes.find((x: { type: string }) => x.type === 'output').fields).toHaveLength(2)
  })
})

describe('the live run in the editor', () => {
  const graph = emptyGraph('notes', 'result', ['Notes', 'Result'])
  const [START, END] = graph.nodes.map((n) => n.id)
  const FLOW = {
    id: 'f1',
    name: 'My flow',
    current_version: 1,
    graph,
    issues: [],
    created_at: '',
    updated_at: '',
  }
  const run = (id: string, status: string, extra: object = {}) => ({
    id,
    flow_id: 'f1',
    flow_version_id: 'fv1',
    status,
    error_code: null,
    created_at: new Date().toISOString(),
    started_at: new Date().toISOString(),
    finished_at: null,
    inputs: {},
    job_id: null,
    result: null,
    handoffs: [],
    steps: [
      { node_id: START, position: 0, status: 'done', output: { text: 'hi' }, latency_ms: 5 },
      { node_id: END, position: 1, status: 'pending', output: null, latency_ms: null },
    ],
    ...extra,
  })

  function renderEditor() {
    const router = createMemoryRouter([{ path: '/f/:flowId', element: <FlowEditor /> }], {
      initialEntries: ['/f/f1'],
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    return router
  }

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  test('a run starts and is followed in place: editing locks, the result shows, Run again follows the new run, Close unlocks', async () => {
    const user = userEvent.setup()
    const current = { r1: run('r1', 'running') as ReturnType<typeof run> }
    mocks.GET.mockImplementation(async (url: string) => {
      if (url === '/api/v1/flows/{flow_id}') return { data: FLOW }
      if (url === '/api/v1/flow-runs/{run_id}') return { data: Object.values(current).at(-1) }
      if (url === '/api/v1/radar/usage') return { data: { used: 1, quota: 50, radar_stops_at: 40 } }
      return { data: [] }
    })
    mocks.POST.mockImplementation(async (url: string) => {
      if (url === '/api/v1/flows/{flow_id}/runs') return { data: run('r1', 'running') }
      if (url === '/api/v1/flow-runs/{run_id}/rerun') {
        Object.assign(current, { r2: run('r2', 'running') })
        return { data: run('r2', 'running') }
      }
      return { data: { issues: [] } }
    })
    const router = renderEditor()
    await user.click(await screen.findByRole('button', { name: 'Run flow' }))
    await user.type(await screen.findByLabelText('Notes'), 'hello')
    await user.click(screen.getByRole('button', { name: 'Watch it run' }))

    // still on the editor, with the live panel and a locked editor
    const panel = await screen.findByRole('region', { name: 'Live run' })
    expect(router.state.location.pathname).toBe('/f/f1')
    expect(screen.getByText(/editing is paused/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open full page' })).toHaveAttribute(
      'href',
      '/automations/runs/r1',
    )
    expect(panel).toHaveTextContent('Running')

    // the run finishes: the answer is shown and can be run again
    current.r1 = run('r1', 'done', {
      result: { text: 'Dear team' },
      finished_at: new Date().toISOString(),
    })
    expect(await screen.findByText('Dear team', undefined, { timeout: 4000 })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Run again' }))
    await waitFor(() =>
      expect(mocks.POST.mock.calls.some((c) => c[0] === '/api/v1/flow-runs/{run_id}/rerun')).toBe(
        true,
      ),
    )
    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'Open full page' })).toHaveAttribute(
        'href',
        '/automations/runs/r2',
      ),
    )

    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('region', { name: 'Live run' })).not.toBeInTheDocument()
    expect(screen.queryByText(/editing is paused/)).not.toBeInTheDocument()
  })

  test('a helper step can be tested on its own with its pinned spec', async () => {
    const user = userEvent.setup()
    mocks.GET.mockResolvedValue({ data: { used: 1, quota: 50, radar_stops_at: 40 } })
    const spec = {
      role: 'custom' as const,
      instructions: 'x',
      model_tier: 'fast' as const,
      inputs: [{ name: 'notes', label: 'Notes', required: true }],
      context_sources: [],
      output: { kind: 'text' as const, fields: [] },
    }
    const g = {
      ...graph,
      nodes: [...graph.nodes, { type: 'agent', id: 'n1', agent_id: 'a1', agent_version_id: 'v1' }],
    } as typeof graph
    const client = new QueryClient()
    render(
      <QueryClientProvider client={client}>
        <RouterProvider
          router={createMemoryRouter([
            {
              path: '/',
              element: (
                <NodeInspector
                  graph={g}
                  node={g.nodes[2]}
                  title="Mira"
                  spec={spec}
                  onGraph={vi.fn()}
                />
              ),
            },
          ])}
        />
      </QueryClientProvider>,
    )
    expect(screen.queryByLabelText('Notes')).not.toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Test this step' }))
    expect(await screen.findByLabelText('Notes')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run' })).toBeDisabled() // the sample text is required
  })
})

test('a waiting run says when it wakes up and can be stopped', async () => {
  const run = {
    id: 'r3',
    flow_id: 'f1',
    flow_version_id: 'fv1',
    status: 'waiting',
    error_code: null,
    wake_at: '2030-01-01T10:00:00Z',
    created_at: '2026-11-02T10:00:00Z',
    started_at: '2026-11-02T10:00:00Z',
    finished_at: null,
    inputs: {},
    job_id: null,
    result: null,
    handoffs: [],
    steps: [],
  }
  mocks.GET.mockImplementation(async (url: string) =>
    url === '/api/v1/flow-runs/{run_id}' ? { data: run } : { data: [] },
  )
  open(<RunPage />, '/automations/runs/:runId', '/automations/runs/r3')
  expect(await screen.findByText(/Waiting until/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Stop/ })).toBeInTheDocument()
})
