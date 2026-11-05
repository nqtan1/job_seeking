import '@xyflow/react/dist/style.css'
import {
  Background,
  BaseEdge,
  type Connection,
  Controls,
  type Edge,
  EdgeLabelRenderer,
  type EdgeProps,
  Handle,
  MarkerType,
  MiniMap,
  type Node,
  type NodeChange,
  type NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
  getBezierPath,
  useReactFlow,
} from '@xyflow/react'
import { type Dispatch, type SetStateAction, useEffect, useMemo, useRef, useState } from 'react'
import { useT } from '@/i18n'
import { Avatar } from './Avatar'
import { type AvatarSpec, type Mood, PALETTES } from './avatar'
import {
  type Graph,
  type GraphNode,
  type Refusal,
  type Specs,
  connect,
  moveNode,
  outputsOf,
  refusal,
  removeEdge,
  removeNode,
  typeKey,
} from './graph'
import { KIND } from './nodeKind'

export type Selection = { kind: 'node' | 'edge'; id: string } | null

type StepData = {
  node: GraphNode
  title: string
  avatar?: AvatarSpec
  mood: Mood
  statusLabel: string
  outs: string[]
  [k: string]: unknown
}
type FlowEdgeData = {
  packet?: number
  accent: string
  light: string
  dark: string
  label: string
  [k: string]: unknown
}

const KIND_HEX: Record<GraphNode['type'], [string, string]> = {
  input: ['#059669', '#34d399'],
  output: ['#4f46e5', '#a5b4fc'],
  condition: ['#b45309', '#fbbf24'],
  transform: ['#64748b', '#cbd5e1'],
  tool: ['#0f766e', '#5eead4'],
  agent: ['#64748b', '#cbd5e1'],
}
const paletteOf = (a?: AvatarSpec) => PALETTES[a?.palette ?? 8] ?? PALETTES[8]
/** [on light, on dark] accent of a step: its helper's palette, or the colour of its kind. */
const colorsOf = (n: GraphNode | undefined, a?: AvatarSpec): [string, string] =>
  n && n.type !== 'agent' ? KIND_HEX[n.type] : [paletteOf(a).accent, paletteOf(a).fill]

/** Follows the app theme (a class on <html>), so colours that must be hex re-render on a switch. */
function useDark() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  useEffect(() => {
    const el = document.documentElement
    const mo = new MutationObserver(() => setDark(el.classList.contains('dark')))
    mo.observe(el, { attributes: true, attributeFilter: ['class'] })
    return () => mo.disconnect()
  }, [])
  return dark
}

function StepNode({ data, selected }: NodeProps<Node<StepData>>) {
  const n = data.node
  const t = useT()
  const { icon: Icon, cls } = KIND[n.type]
  const p = paletteOf(data.avatar)
  return (
    <div
      style={
        n.type === 'agent'
          ? ({ '--kl': p.accent, '--kd': p.fill } as React.CSSProperties)
          : undefined
      }
      className={`kind ${cls} step-node relative w-[220px] rounded-xl border bg-card py-2.5 pr-3 pl-4 text-card-foreground shadow-sm`}
      data-selected={!!selected}
    >
      <span
        aria-hidden
        className="absolute inset-y-0 left-0 w-1.5 rounded-l-xl"
        style={{ background: 'var(--k)' }}
      />
      {n.type !== 'input' && <Handle type="target" position={Position.Left} id="in" />}
      <p
        className="flex items-center gap-1 text-[10px] font-semibold tracking-wider uppercase"
        style={{ color: 'var(--k)' }}
      >
        <Icon aria-hidden className="size-3" />
        {t(typeKey(n.type))}
      </p>
      <div className="mt-1.5 flex items-center gap-2.5">
        {data.avatar && <Avatar spec={data.avatar} mood={data.mood} size={36} />}
        <div className="min-w-0">
          <p className="truncate text-sm leading-tight font-medium">{data.title}</p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{data.statusLabel}</p>
        </div>
      </div>
      {data.outs.length > 0 && n.type !== 'output' && (
        <p className="mt-1.5 truncate font-mono text-[10px] text-muted-foreground">
          → {data.outs.slice(0, 3).join(', ')}
          {data.outs.length > 3 ? ` +${data.outs.length - 3}` : ''}
        </p>
      )}
      {n.type === 'condition' ? (
        <>
          <Handle type="source" position={Position.Right} id="true" style={{ top: '30%' }} />
          <Handle type="source" position={Position.Right} id="false" style={{ top: '70%' }} />
        </>
      ) : (
        n.type !== 'output' && <Handle type="source" position={Position.Right} id="out" />
      )}
    </div>
  )
}

function FlowEdge(p: EdgeProps<Edge<FlowEdgeData>>) {
  const [path, lx, ly] = getBezierPath({ ...p, curvature: 0.3 })
  const accent = p.data?.accent ?? '#64748b'
  return (
    <>
      <BaseEdge
        id={p.id}
        path={path}
        markerEnd={p.markerEnd}
        className="flow-edge"
        style={
          {
            '--el': p.data?.light,
            '--ed': p.data?.dark,
            stroke: 'var(--el)',
            strokeWidth: p.selected ? 3 : 2,
            strokeLinecap: 'round',
          } as React.CSSProperties
        }
      />
      {p.data?.packet ? (
        <circle key={p.data.packet} r="6" fill={accent} stroke="white" strokeWidth="2">
          <animateMotion
            dur="0.7s"
            repeatCount="1"
            fill="freeze"
            path={path}
            keyPoints="0;1"
            keyTimes="0;1"
            calcMode="spline"
            keySplines="0.45 0 0.25 1"
          />
        </circle>
      ) : null}
      {p.data?.label ? (
        <EdgeLabelRenderer>
          <span
            style={{ transform: `translate(-50%, -50%) translate(${lx}px, ${ly}px)` }}
            className={`pointer-events-none absolute rounded-full bg-card px-2 py-0.5 text-[11px] leading-4 font-medium text-muted-foreground shadow-sm ring-1 ${p.selected ? 'ring-ring' : 'ring-border'}`}
          >
            {p.data.label}
          </span>
        </EdgeLabelRenderer>
      ) : null}
    </>
  )
}

/** One quiet line under the title: what the step holds, never a repeat of its kind. */
function subtitleOf(n: GraphNode, t: ReturnType<typeof useT>): string {
  switch (n.type) {
    case 'input':
    case 'output':
      return n.fields.map((f) => f.name).join(', ')
    case 'condition':
      return `${t(`helpers.cond.${n.op}`)} “${n.value}”`
    case 'transform':
      return t(`helpers.transform.${n.op}`)
    case 'tool':
      return t(`helpers.tool.${n.tool}.short`)
    default:
      return t('helpers.node.agent')
  }
}
const FIT = { padding: 0.12, maxZoom: 1.15, duration: 250 }
const nodeTypes = { step: StepNode }
const edgeTypes = { flow: FlowEdge }

type CanvasProps = {
  graph: Graph
  specs: Specs
  titles: ReadonlyMap<string, string>
  avatars: ReadonlyMap<string, AvatarSpec>
  /** Per step; leave empty when editing. */
  moods?: ReadonlyMap<string, Mood>
  /** edge id → a counter that restarts its packet animation */
  packets?: ReadonlyMap<string, number>
  statusLabels?: ReadonlyMap<string, string>
  selection: Selection
  readOnly?: boolean
  /** Change it to re-fit the view (after an auto-arrange). */
  fitSignal?: number
  onGraph?: Dispatch<SetStateAction<Graph>>
  onSelect?: (s: Selection) => void
  onRefuse?: (why: Refusal) => void
}

/** The visual editor. The graph is the single source of truth: React Flow only displays it and
 *  reports gestures, which are turned into the same pure graph edits the Steps list uses. */
export default function Canvas(props: CanvasProps) {
  return (
    <ReactFlowProvider>
      <Inner {...props} />
    </ReactFlowProvider>
  )
}

function Inner(p: CanvasProps) {
  const t = useT()
  const { graph, specs, readOnly } = p
  const { fitView } = useReactFlow()
  const dark = useDark()
  // Re-fit after an auto-arrange and whenever a step is added, so steps never end up tiny or
  // off-screen. The short wait lets React Flow measure the new node first.
  const count = graph.nodes.length
  const seen = useRef(count)
  useEffect(() => {
    const grew = count > seen.current
    seen.current = count
    if (!p.fitSignal && !grew) return
    const id = setTimeout(() => fitView(FIT), 60)
    return () => clearTimeout(id)
    // fitSignal / count are the triggers; FIT is a constant
  }, [p.fitSignal, count, fitView])

  const nodes: Node<StepData>[] = useMemo(
    () =>
      graph.nodes.map((n) => ({
        id: n.id,
        type: 'step',
        // the minimap reads these (the editor ignores dimension changes: the graph owns the nodes)
        initialWidth: 220,
        initialHeight: 72,
        position: { x: n.position?.x ?? 0, y: n.position?.y ?? 0 },
        selected: p.selection?.kind === 'node' && p.selection.id === n.id,
        deletable: !readOnly && n.type !== 'input' && n.type !== 'output',
        draggable: !readOnly,
        data: {
          node: n,
          title: p.titles.get(n.id) ?? t(typeKey(n.type)),
          avatar: p.avatars.get(n.id),
          mood: p.moods?.get(n.id) ?? 'idle',
          statusLabel: p.statusLabels?.get(n.id) ?? subtitleOf(n, t),
          outs: outputsOf(n, p.specs),
        },
      })),
    [graph.nodes, p.specs, p.titles, p.avatars, p.moods, p.statusLabels, p.selection, readOnly, t],
  )

  const edges: Edge<FlowEdgeData>[] = useMemo(() => {
    const colors = (id: string) =>
      colorsOf(
        graph.nodes.find((n) => n.id === id),
        p.avatars.get(id),
      )
    return graph.edges.map((e) => ({
      id: e.id,
      source: e.from.node,
      sourceHandle: e.from.port ?? 'out',
      target: e.to,
      targetHandle: 'in',
      type: 'flow',
      selected: p.selection?.kind === 'edge' && p.selection.id === e.id,
      deletable: !readOnly,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 16,
        height: 16,
        color: colors(e.from.node)[dark ? 1 : 0],
      },
      data: {
        packet: p.packets?.get(e.id),
        accent: colors(e.from.node)[dark ? 1 : 0],
        light: colors(e.from.node)[0],
        dark: colors(e.from.node)[1],
        label:
          e.from.port === 'true' || e.from.port === 'false'
            ? t(`helpers.port.${e.from.port}`)
            : e.map.map((m) => m.input).join(', '),
      },
    }))
  }, [graph.edges, graph.nodes, p.packets, p.avatars, p.selection, readOnly, t, dark])

  const onNodesChange = (changes: NodeChange<Node<StepData>>[]) => {
    if (readOnly || !p.onGraph) return
    for (const c of changes)
      if (c.type === 'select' && c.selected) p.onSelect?.({ kind: 'node', id: c.id })
    // applied on top of the latest graph, so two gestures in one frame cannot lose each other
    p.onGraph((g) => {
      let next = g
      for (const c of changes) {
        if (c.type === 'position' && c.position)
          next = moveNode(next, c.id, c.position.x, c.position.y)
        else if (c.type === 'remove') {
          const n = next.nodes.find((x) => x.id === c.id)
          if (n && n.type !== 'input' && n.type !== 'output') next = removeNode(next, c.id)
        }
      }
      return next === g ? g : next
    })
  }

  const onConnect = (c: Connection) => {
    if (readOnly || !p.onGraph || !c.source || !c.target) return
    const port = (c.sourceHandle ?? 'out') as 'out' | 'true' | 'false'
    const r = connect(graph, c.source, port, c.target, specs)
    if (r.refused) p.onRefuse?.(r.refused)
    else {
      p.onGraph(r.graph)
      if (r.edge) p.onSelect?.({ kind: 'edge', id: r.edge.id })
    }
  }

  return (
    <div
      className="flow-canvas h-[clamp(22rem,48vh,36rem)] w-full overflow-hidden rounded-xl border bg-muted/30"
      role="application"
      aria-label={t('helpers.canvas')}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={FIT}
        minZoom={0.3}
        maxZoom={1.5}
        nodesConnectable={!readOnly}
        elementsSelectable
        deleteKeyCode={readOnly ? null : ['Backspace', 'Delete']}
        onNodesChange={onNodesChange}
        onEdgesChange={(changes) => {
          if (readOnly || !p.onGraph) return
          for (const c of changes)
            if (c.type === 'select' && c.selected) p.onSelect?.({ kind: 'edge', id: c.id })
          p.onGraph((g) => {
            let next = g
            for (const c of changes) if (c.type === 'remove') next = removeEdge(next, c.id)
            return next === g ? g : next
          })
        }}
        onConnect={onConnect}
        isValidConnection={(c) =>
          !!c.source &&
          !!c.target &&
          refusal(graph, c.source, (c.sourceHandle ?? 'out') as string, c.target) === null
        }
        onPaneClick={() => p.onSelect?.(null)}
      >
        <Background gap={22} size={1.2} />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          ariaLabel={t('helpers.minimap')}
          nodeColor={(n) => {
            const d = n.data as StepData
            return colorsOf(d.node, d.avatar)[dark ? 1 : 0]
          }}
          nodeStrokeWidth={0}
          nodeBorderRadius={4}
          style={{ width: 150, height: 100 }}
          bgColor="var(--card)"
          maskColor="color-mix(in oklch, var(--foreground) 7%, transparent)"
          className="!hidden sm:!block"
        />
      </ReactFlow>
    </div>
  )
}
