import '@/features/helpers/lib'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { NodeInspector } from '@/features/helpers/FlowPanels'
import { typeableInputs, type Graph } from '@/features/helpers/graph'

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

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

it('never offers an address or the engine list to be typed', () => {
  expect(typeableInputs('read_page')).toEqual([])
  expect(typeableInputs('for_each')).toEqual([])
  expect(typeableInputs('find_offers')).toEqual(['query', 'department'])
})
