import {
  type Graph,
  type GraphNode,
  type Specs,
  type VersionSpec,
  addNode,
  aiCalls,
  autoMap,
  cloneNodes,
  connect,
  emptyGraph,
  freeName,
  MAX_NODES,
  inputsOf,
  moveNode,
  outputsOf,
  removeNode,
} from '@/features/helpers/graph'
import {
  CATCH_UP_MS,
  beatsBetween,
  moodsAfter,
  replayFrames,
  spacing,
} from '@/features/helpers/playback'
import { avatarFromSeed, safe } from '@/features/helpers/avatar'

const spec: VersionSpec = {
  role: 'custom',
  instructions: 'x',
  model_tier: 'fast',
  inputs: [
    { name: 'notes', label: 'Notes', required: true },
    { name: 'extra', label: 'Extra', required: false },
  ],
  context_sources: [],
  output: { kind: 'text', fields: [] },
}
const agent = (id: string): GraphNode => ({
  type: 'agent',
  id,
  agent_id: 'a-' + id,
  agent_version_id: 'v1',
  position: { x: 0, y: 0 },
})
const specs: Specs = new Map([['v1', spec]])
const base = (): Graph => emptyGraph('notes', 'result', ['Notes', 'Result'])

test('steps are limited, unique in kind, and removing one removes its connections', () => {
  let g = base()
  const [i, o] = g.nodes
  expect(addNode(g, { ...i, id: 'second-input' })).toBe(g) // one Input only
  g = addNode(g, agent('a'))
  g = connect(g, i.id, 'out', 'a', specs).graph
  g = connect(g, 'a', 'out', o.id, specs).graph
  expect(g.edges).toHaveLength(2)
  const gone = removeNode(g, 'a')
  expect(gone.edges).toEqual([]) // nothing dangles
  for (let n = 0; n < 20; n++) g = addNode(g, agent('x' + n))
  expect(g.nodes).toHaveLength(MAX_NODES)
})

test('a connection is refused with a reason instead of being silently dropped', () => {
  let g = addNode(base(), agent('a'))
  g = addNode(g, agent('b'))
  const [i, o] = g.nodes
  expect(connect(g, 'a', 'out', 'a', specs).refused).toBe('same_step')
  expect(connect(g, o.id, 'out', 'a', specs).refused).toBe('from_output')
  expect(connect(g, 'a', 'out', i.id, specs).refused).toBe('to_input')
  g = connect(g, 'a', 'out', 'b', specs).graph
  expect(connect(g, 'a', 'out', 'b', specs).refused).toBe('duplicate')
  expect(connect(g, 'b', 'out', 'a', specs).refused).toBe('cycle')
})

test('obvious mappings are filled in, ambiguous ones are left to the user', () => {
  const g = addNode(base(), agent('a'))
  const [i] = g.nodes
  const a = g.nodes[2]
  // same name on both sides ("notes")
  expect(autoMap(i, a, specs, new Set())).toEqual([{ input: 'notes', value: '{{notes}}' }])
  // one output into the one required input
  const t = agent('t')
  expect(autoMap(t, a, specs, new Set())).toEqual([{ input: 'notes', value: '{{text}}' }])
  // the declared input is already fed: the rest goes through the optional "info" input
  expect(autoMap(t, a, specs, new Set(['notes']))).toEqual([
    { input: 'info', value: 'text: {{text}}' },
  ])
  expect(inputsOf(a, specs).map((x) => x.name)).toEqual(['notes', 'extra', 'info'])
  expect(outputsOf(a, specs)).toEqual(['text'])
})

test('duplicating steps gives new ids and keeps only the connections between the copies', () => {
  let g = addNode(addNode(base(), agent('a')), agent('b'))
  g = connect(g, 'a', 'out', 'b', specs).graph
  g = connect(g, g.nodes[0].id, 'out', 'a', specs).graph
  const copy = cloneNodes(g, ['a', 'b'])
  const ids = new Set(copy.nodes.map((n) => n.id))
  expect(ids.size).toBe(copy.nodes.length) // no id reused
  expect(copy.nodes).toHaveLength(g.nodes.length + 2)
  expect(copy.edges).toHaveLength(g.edges.length + 1) // only the a→b link is copied
  for (const e of copy.edges) expect(ids.has(e.to) && ids.has(e.from.node)).toBe(true)
  expect(aiCalls(copy)).toBe(4)
  expect(moveNode(g, 'a', 5, 6).nodes.find((n) => n.id === 'a')!.position).toEqual({ x: 5, y: 6 })
})

test('catching up plays changes in execution order, fits the budget and ends on the truth', () => {
  const prev = [
    { node_id: 'i', position: 0, status: 'pending' },
    { node_id: 'a', position: 1, status: 'pending' },
    { node_id: 'o', position: 2, status: 'pending' },
  ]
  const next = [
    { node_id: 'o', position: 2, status: 'done' },
    { node_id: 'a', position: 1, status: 'done' },
    { node_id: 'i', position: 0, status: 'done' },
  ]
  const beats = beatsBetween(prev, next)
  expect(beats.map((b) => b.node)).toEqual(['i', 'a', 'o'])
  expect(spacing(beats.length) * beats.length).toBeLessThanOrEqual(CATCH_UP_MS)
  expect(spacing(40) * 40).toBeLessThanOrEqual(CATCH_UP_MS)
  expect(moodsAfter(prev, beats, 1).get('i')).toBe('done')
  expect(moodsAfter(prev, beats, 1).get('a')).toBe('queued')
  expect([...moodsAfter(prev, beats, beats.length).values()]).toEqual(['done', 'done', 'done'])
  expect(beatsBetween(next, next)).toEqual([]) // an unchanged poll plays nothing
  expect(replayFrames(next)).toHaveLength(3)
})

test('an avatar is stable for a seed and always drawable', () => {
  expect(avatarFromSeed('followup')).toEqual(avatarFromSeed('followup'))
  expect(avatarFromSeed('followup')).not.toEqual(avatarFromSeed('pitch'))
  const wild = safe({ seed: 'x', body: 99, palette: -4, eyes: 7.9, accessory: NaN })
  expect(wild).toMatchObject({ body: 7, palette: 0, eyes: 5, accessory: 0 })
})

test('linking waits for a helper whose spec is still loading, instead of leaving an empty mapping', () => {
  const g = addNode(base(), agent('a'))
  const [i] = g.nodes
  const none: Specs = new Map() // the spec of version v1 has not arrived yet
  expect(connect(g, i.id, 'out', 'a', none).refused).toBe('loading')
  expect(connect(g, i.id, 'out', 'a', specs).edge?.map).toEqual([
    { input: 'notes', value: '{{notes}}' },
  ])
})

test('a new field or input never reuses a name that is still taken', () => {
  expect(freeName('field', ['field_1', 'field_3'])).toBe('field_4')
  expect(freeName('field', ['notes', 'field_2', 'field_3'])).toBe('field_4')
  expect(freeName('field', [])).toBe('field_1')
})
