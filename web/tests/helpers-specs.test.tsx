import '@/features/helpers/lib'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { useSpecs } from '@/features/helpers/api'
import type { Graph, VersionSpec } from '@/features/helpers/graph'

const mocks = vi.hoisted(() => ({ GET: vi.fn() }))
vi.mock('@/lib/api/client', () => ({ api: mocks }))

const spec = (name: string): VersionSpec => ({
  role: 'custom',
  instructions: name,
  model_tier: 'fast',
  inputs: [],
  context_sources: [],
  output: { kind: 'text', fields: [] },
})

it('asks again when the cached versions of a helper lack the version the flow pins', async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  // cached before the helper's newest version was saved
  qc.setQueryData(['helpers', 'a1', 'versions'], [{ id: 'v1', spec: spec('old') }], {
    updatedAt: Date.now(),
  })
  mocks.GET.mockResolvedValue({
    data: [
      { id: 'v1', spec: spec('old') },
      { id: 'v2', spec: spec('new') },
    ],
  })
  const graph = {
    schema_version: 1,
    edges: [],
    nodes: [
      { type: 'agent', id: 'n1', agent_id: 'a1', agent_version_id: 'v2', position: { x: 0, y: 0 } },
    ],
  } as unknown as Graph
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(() => useSpecs(graph), { wrapper })
  await waitFor(() => expect(result.current.ready).toBe(true))
  expect(mocks.GET).toHaveBeenCalledTimes(1)
  expect(result.current.specs.get('v2')?.instructions).toBe('new')
})
