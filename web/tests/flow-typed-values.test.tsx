import '@/features/helpers/lib'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, renderHook, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { NodeInspector } from '@/features/helpers/FlowPanels'
import { useToolTable } from '@/features/helpers/api'
import { inputsOf, outputsOf, typeableInputs, type Graph } from '@/features/helpers/graph'
import { outputFields } from '@/features/helpers/samples'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))
vi.mock('@/features/settings/api', () => ({ useMe: () => ({ data: { helpers_enabled: true } }) }))

const tool = (id: string, inputs: [string, boolean][], outputs: string[]) => ({
  id,
  pack: 'x',
  inputs: inputs.map(([name, required]) => ({ name, required })),
  outputs,
  effect: 'read',
  ai_uses: 0,
  daily_cap: null,
  needs_job: false,
  chat: false,
  page: null,
})

beforeAll(async () => {
  mocks.GET.mockResolvedValue({
    data: [
      tool(
        'find_offers',
        [
          ['query', true],
          ['department', false],
        ],
        ['items', 'count'],
      ),
      tool('read_page', [['url', true]], ['text']),
      tool('for_each', [['items', true]], ['started']),
      tool('save_note', [['text', true]], ['note_id']), // a pack tool the editor has no sample for
    ],
  })
  const { result } = renderHook(() => useToolTable(), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
    ),
  })
  await waitFor(() => expect(result.current.data).toBeDefined())
})

const node = {
  type: 'tool',
  id: 'n1',
  tool: 'find_offers',
  fixed: {},
  position: { x: 0, y: 0 },
} as never
const graph = { schema_version: 1, nodes: [node], edges: [] } as unknown as Graph

it('lets the keywords of a search be typed on the step itself', async () => {
  const onGraph = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <NodeInspector graph={graph} node={node} title="Find new job offers" onGraph={onGraph} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  await userEvent.type(screen.getByLabelText('Search'), 'A')
  expect(onGraph).toHaveBeenLastCalledWith(
    expect.objectContaining({
      nodes: [expect.objectContaining({ id: 'n1', fixed: { query: 'A' } })],
    }),
  )
})

it('takes the ports of every step from GET /tools, with a generic example for a new tool', () => {
  const note = { ...(node as object), tool: 'save_note' } as never
  expect(inputsOf(note, new Map())).toEqual([{ name: 'text', required: true }])
  expect(outputsOf(note, new Map())).toEqual(['note_id'])
  expect(outputFields(note, new Map())).toEqual([{ name: 'note_id', example: '…' }])
  expect(inputsOf({ ...(node as object), tool: 'gone' } as never, new Map())).toEqual([])
})

it('never offers an address or the engine list to be typed', () => {
  expect(typeableInputs('read_page')).toEqual([])
  expect(typeableInputs('for_each')).toEqual([])
  expect(typeableInputs('find_offers')).toEqual(['query', 'department'])
})
