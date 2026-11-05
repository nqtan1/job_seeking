import type { components } from '@/lib/api/schema'

type S = components['schemas']
export type Graph = S['Graph']
export type GraphNode = Graph['nodes'][number]
type GraphEdge = S['Edge']
export type VersionSpec = S['VersionSpec']
export type MapEntry = S['MapEntry']
export type Issue = S['IssueOut']

/** Pure editing rules for the flow graph. The server validates everything again; these keep the
 *  editor from producing obviously broken graphs and tell the user why a connection is refused. */

export type Specs = ReadonlyMap<string, VersionSpec> // agent_version_id -> spec

/** What each action block takes and gives (backend graph.TOOLS; backend/tests/unit/test_limits_in_sync.py
 *  fails if the names drift). Inputs are `[name, required]`. */
export const TOOL_IO = {
  web_search: { in: [['query', true]], out: ['text', 'sources'] },
  job_search: {
    in: [
      ['query', true],
      ['department', false],
    ],
    out: ['text', 'count'],
  },
  find_offers: {
    in: [
      ['query', true],
      ['department', false],
    ],
    out: ['items', 'text', 'count', 'remaining'],
  },
  fit_check: {
    in: [
      ['start', false],
      ['employer', false],
    ],
    out: ['score', 'verdict', 'strengths', 'gaps', 'missing', 'reasons'],
  },
  for_each: { in: [['items', true]], out: ['started', 'text'] },
  read_page: { in: [['url', true]], out: ['text'] },
  job_lookup: { in: [['start', false]], out: ['title', 'company', 'place', 'description', 'url'] },
  add_to_tracker: {
    in: [
      ['company', true],
      ['title', false],
      ['url', false],
      ['notes', false],
    ],
    out: ['status'],
  },
  send_email: {
    in: [
      ['to', true],
      ['subject', true],
      ['body', true],
    ],
    out: ['status'],
  },
  wait: { in: [['value', true]], out: ['value'] },
} as const satisfies Record<
  string,
  { in: readonly (readonly [string, boolean])[]; out: readonly string[] }
>
type ToolKind = keyof typeof TOOL_IO
export const TOOL_KINDS = Object.keys(TOOL_IO) as ToolKind[]

export function inputsOf(node: GraphNode, specs: Specs): { name: string; required: boolean }[] {
  switch (node.type) {
    case 'output':
      return node.fields.map((f) => ({ name: f.name, required: false }))
    case 'agent': {
      const own = (specs.get(node.agent_version_id)?.inputs ?? []).map((i) => ({
        name: i.name,
        required: i.required ?? true,
      }))
      // Every helper also takes "info" (backend graph.EXTRA_INPUT): anything can be handed to it.
      return specs.has(node.agent_version_id) && !own.some((i) => i.name === EXTRA_INPUT)
        ? [...own, { name: EXTRA_INPUT, required: false }]
        : own
    }
    case 'condition':
      return [{ name: 'value', required: true }]
    case 'transform':
      return [{ name: 'text', required: true }]
    case 'tool':
      return TOOL_IO[node.tool].in.map(([name, required]) => ({ name, required }))
    default:
      return []
  }
}

export function outputsOf(node: GraphNode, specs: Specs): string[] {
  switch (node.type) {
    case 'input':
      return node.fields.map((f) => f.name)
    case 'agent': {
      const out = specs.get(node.agent_version_id)?.output
      if (!out) return []
      return out.kind === 'text' ? ['text'] : (out.fields ?? []).map((f) => f.name)
    }
    case 'condition':
      return ['value']
    case 'transform':
      return ['text']
    case 'tool':
      return [...TOOL_IO[node.tool].out]
    default:
      return []
  }
}

export const EXTRA_INPUT = 'info'

export const newId = () => crypto.randomUUID()

export function addNode(g: Graph, node: GraphNode): Graph {
  if (g.nodes.length >= MAX_NODES) return g
  if (node.type === 'input' && g.nodes.some((n) => n.type === 'input')) return g
  if (node.type === 'output' && g.nodes.some((n) => n.type === 'output')) return g
  return { ...g, nodes: [...g.nodes, node] }
}

/** Removing a step removes every connection to it: no edge may point at nothing. */
export function removeNode(g: Graph, id: string): Graph {
  return {
    ...g,
    nodes: g.nodes.filter((n) => n.id !== id),
    edges: g.edges.filter((e) => e.from.node !== id && e.to !== id),
  }
}

export const moveNode = (g: Graph, id: string, x: number, y: number): Graph => ({
  ...g,
  nodes: g.nodes.map((n) => (n.id === id ? { ...n, position: { x, y } } : n)),
})

export const patchNode = (g: Graph, id: string, patch: Partial<GraphNode>): Graph => ({
  ...g,
  nodes: g.nodes.map((n) => (n.id === id ? ({ ...n, ...patch } as GraphNode) : n)),
})

export function reaches(g: Graph, from: string, to: string): boolean {
  const seen = new Set<string>()
  const stack = [from]
  while (stack.length) {
    const cur = stack.pop()!
    if (cur === to) return true
    if (seen.has(cur)) continue
    seen.add(cur)
    for (const e of g.edges) if (e.from.node === cur) stack.push(e.to)
  }
  return false
}

export type Refusal =
  | 'same_step'
  | 'duplicate'
  | 'from_output'
  | 'to_input'
  | 'cycle'
  | 'too_many'
  | 'missing'
  | 'loading'

/** Why this connection cannot be made, or null. Shown to the user, never silently ignored. */
export function refusal(g: Graph, from: string, port: string, to: string): Refusal | null {
  const a = g.nodes.find((n) => n.id === from)
  const b = g.nodes.find((n) => n.id === to)
  if (!a || !b) return 'missing'
  if (from === to) return 'same_step'
  if (a.type === 'output') return 'from_output'
  if (b.type === 'input') return 'to_input'
  if (g.edges.length >= MAX_EDGES) return 'too_many'
  if (g.edges.some((e) => e.from.node === from && e.from.port === port && e.to === to))
    return 'duplicate'
  if (reaches(g, to, from)) return 'cycle'
  return null
}

/** Pre-fill what is obvious: same names map to each other; one output into one required input. */
export function autoMap(
  from: GraphNode,
  to: GraphNode,
  specs: Specs,
  taken: ReadonlySet<string>,
): MapEntry[] {
  const outs = outputsOf(from, specs)
  const ins = inputsOf(to, specs).filter((i) => !taken.has(i.name))
  const byName = ins.filter((i) => outs.includes(i.name))
  if (byName.length) return byName.map((i) => ({ input: i.name, value: `{{${i.name}}}` }))
  const required = ins.filter((i) => i.required)
  if (outs.length === 1 && required.length === 1)
    return [{ input: required[0].name, value: `{{${outs[0]}}}` }]
  if (to.type === 'output' && outs.length === 1 && ins.length === 1)
    return [{ input: ins[0].name, value: `{{${outs[0]}}}` }]
  // Nothing declared to fill: hand over what the step gave, labelled, through the optional input.
  if (to.type === 'agent' && ins.some((i) => i.name === EXTRA_INPUT) && outs.length)
    return [{ input: EXTRA_INPUT, value: outs.map((o) => `${o}: {{${o}}}`).join('\n') }]
  return []
}

export function connect(
  g: Graph,
  from: string,
  port: 'out' | 'true' | 'false',
  to: string,
  specs: Specs,
): { graph: Graph; edge?: GraphEdge; refused?: Refusal } {
  const why = refusal(g, from, port, to)
  if (why) return { graph: g, refused: why }
  const a = g.nodes.find((n) => n.id === from)!
  const b = g.nodes.find((n) => n.id === to)!
  // A helper's inputs and outputs are only known once its spec has loaded: linking before that
  // would leave an empty mapping that never fills itself in.
  const unknown = (n: GraphNode) => n.type === 'agent' && !specs.has(n.agent_version_id)
  if (unknown(a) || unknown(b)) return { graph: g, refused: 'loading' }
  const taken = new Set(
    g.edges.filter((e) => e.to === to).flatMap((e) => e.map.map((m) => m.input)),
  )
  const edge: GraphEdge = {
    id: newId(),
    from: { node: from, port },
    to,
    map: autoMap(a, b, specs, taken),
  }
  return { graph: { ...g, edges: [...g.edges, edge] }, edge }
}

export const removeEdge = (g: Graph, id: string): Graph => ({
  ...g,
  edges: g.edges.filter((e) => e.id !== id),
})

export const setMap = (g: Graph, id: string, map: MapEntry[]): Graph => ({
  ...g,
  edges: g.edges.map((e) => (e.id === id ? { ...e, map } : e)),
})

/** Model calls a run can make: one per helper and one per web search (backend flows.ai_calls). */
export const aiCalls = (g: Graph) =>
  g.nodes.filter(
    (n) =>
      n.type === 'agent' ||
      (n.type === 'tool' && (n.tool === 'web_search' || n.tool === 'fit_check')),
  ).length

/** Copy steps with fresh ids and the connections between them remapped (paste / duplicate). */
export function cloneNodes(g: Graph, ids: string[], dx = 40, dy = 40): Graph {
  const room = MAX_NODES - g.nodes.length
  const picked = g.nodes
    .filter((n) => ids.includes(n.id) && n.type !== 'input' && n.type !== 'output')
    .slice(0, Math.max(room, 0))
  const map = new Map(picked.map((n) => [n.id, newId()]))
  const copies = picked.map((n) => ({
    ...n,
    id: map.get(n.id)!,
    position: { x: (n.position?.x ?? 0) + dx, y: (n.position?.y ?? 0) + dy },
  })) as GraphNode[]
  const edges = g.edges
    .filter((e) => map.has(e.from.node) && map.has(e.to))
    .map((e) => ({
      ...e,
      id: newId(),
      from: { ...e.from, node: map.get(e.from.node)! },
      to: map.get(e.to)!,
    }))
  return { ...g, nodes: [...g.nodes, ...copies], edges: [...g.edges, ...edges] }
}

export function emptyGraph(inputName: string, outputName: string, labels: [string, string]): Graph {
  return {
    schema_version: 1,
    nodes: [
      {
        type: 'input',
        id: newId(),
        position: { x: 0, y: 120 },
        fields: [{ name: inputName, label: labels[0], required: true }],
      },
      {
        type: 'output',
        id: newId(),
        position: { x: 680, y: 120 },
        fields: [{ name: outputName, label: labels[1], required: true }],
      },
    ],
    edges: [],
  }
}

/** Execution order for display (the same rule as the server: a step comes after its sources). */
export function orderOf(g: Graph): string[] {
  const indeg = new Map(g.nodes.map((n) => [n.id, 0]))
  for (const e of g.edges) if (indeg.has(e.to)) indeg.set(e.to, (indeg.get(e.to) ?? 0) + 1)
  const ready = g.nodes.filter((n) => indeg.get(n.id) === 0).map((n) => n.id)
  const out: string[] = []
  while (ready.length) {
    const id = ready.shift()!
    out.push(id)
    for (const e of g.edges)
      if (e.from.node === id) {
        indeg.set(e.to, (indeg.get(e.to) ?? 1) - 1)
        if (indeg.get(e.to) === 0) ready.push(e.to)
      }
  }
  // A cycle (the server reports it) leaves some steps out: show them last, never lose them.
  return [...out, ...g.nodes.map((n) => n.id).filter((id) => !out.includes(id))]
}

/** Left-to-right layers by distance from the start; steps in a layer are stacked. */
export function autoLayout(g: Graph, dx = 320, dy = 130): Graph {
  const depth = new Map<string, number>()
  for (const id of orderOf(g)) {
    const into = g.edges.filter((e) => e.to === id).map((e) => depth.get(e.from.node) ?? 0)
    depth.set(id, into.length ? Math.max(...into) + 1 : 0)
  }
  const rows = new Map<number, number>()
  return {
    ...g,
    nodes: g.nodes.map((n) => {
      const d = depth.get(n.id) ?? 0
      const r = rows.get(d) ?? 0
      rows.set(d, r + 1)
      return { ...n, position: { x: d * dx, y: r * dy } }
    }),
  }
}

/** First unused `prefix_N`: a removed row never makes the next added one collide. */
export const freeName = (prefix: string, taken: string[]) => {
  let n = taken.length + 1
  while (taken.includes(`${prefix}_${n}`)) n++
  return `${prefix}_${n}`
}

/** Ids for a "Send to…" list: the Result step always last, the rest keep their order. */
export function resultLast(g: Graph, ids: string[]): string[] {
  const isOut = (id: string) => g.nodes.find((n) => n.id === id)?.type === 'output'
  return [...ids.filter((id) => !isOut(id)), ...ids.filter(isOut)]
}

/** A step's own name: the transform is "Clean text" for people, whatever its stored type says. */
export const typeKey = (type: GraphNode['type']) =>
  type === 'transform'
    ? ('helpers.node.transform_name' as const)
    : (`helpers.node.${type}` as const)

/** Limits the server enforces (backend/src/recruitai/modules/agents/schemas.py and graph.py).
 *  The UI uses them only as hints; backend/tests/unit/test_limits_in_sync.py fails if they drift. */
export const MAX_INPUT_CHARS = 20_000
export const MAX_INPUTS = 6
export const MAX_FIELDS = 12
export const MAX_NODES = 15
export const MAX_EDGES = 30
export const MAX_HELPERS = 20 // backend service.MAX_AGENTS_PER_ORG
export const MAX_SCHEDULES = 5 // backend schedules.MAX_SCHEDULES_PER_ORG
