import { CircleCheck, LayoutGrid, ListOrdered, Lock, Play, Save, Workflow } from 'lucide-react'
import { type Dispatch, type SetStateAction, Suspense, lazy, useState } from 'react'
import { useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { ListSkeleton } from '@/components/Skeleton'
import { Spinner } from '@/components/Spinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { type Agent, type FlowDetail, type Run, useFetchAgent, type usePatchFlow } from './api'
import { ConflictBanner } from './ui'
import { EdgeInspector, NodeInspector } from './FlowPanels'
import {
  type Graph,
  type GraphNode,
  MAX_NODES,
  type Refusal,
  type Specs,
  addNode,
  autoLayout,
  newId,
} from './graph'
import { LiveRunPanel } from './RunParts'
import { StepsList } from './StepsList'
import type { Selection } from './Canvas'
import type { AvatarSpec, Mood } from './avatar'
import { AddMenu } from './AddMenu'

const Canvas = lazy(() => import('./Canvas')) // React Flow is large: only this page pays for it

export type View = 'canvas' | 'steps'
type SetGraph = Dispatch<SetStateAction<Graph>>
type Labels = { titles: ReadonlyMap<string, string>; avatars: ReadonlyMap<string, AvatarSpec> }

/** Saved state, "Save version" and "Run" in the page header. */
export function RunActions({
  dirty,
  base,
  saving,
  canRun,
  hint,
  onSave,
  onRun,
}: {
  dirty: boolean
  base: number
  saving: boolean
  canRun: boolean
  hint: string
  onSave: () => void
  onRun: () => void
}) {
  const t = useT()
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span
        role="status"
        className={`flex items-center gap-1.5 text-xs ${dirty ? 'font-medium text-warning' : 'text-muted-foreground'}`}
      >
        {dirty ? (
          <span aria-hidden className="size-1.5 rounded-full bg-warning" />
        ) : (
          <CircleCheck aria-hidden className="size-3.5 text-success" />
        )}
        {dirty ? t('helpers.unsaved') : t('helpers.flow.status_saved')}
      </span>
      <Button variant="outline" onClick={onSave} disabled={!dirty || saving}>
        {saving ? <Spinner /> : <Save data-icon="inline-start" />}
        {t('helpers.save_version')} · v{base}
      </Button>
      <Button
        onClick={onRun}
        disabled={!canRun}
        title={hint || undefined}
        aria-describedby={hint ? 'run-hint' : undefined}
      >
        <Play data-icon="inline-start" />
        {t('helpers.run_flow')}
      </Button>
    </div>
  )
}

/** The flow's name, renamed when the field is left. */
export function NameInput({
  detail,
  patch,
}: {
  detail: FlowDetail
  patch: ReturnType<typeof usePatchFlow>
}) {
  const t = useT()
  const [name, setName] = useState(detail.name)
  return (
    <Input
      aria-label={t('helpers.name')}
      className="h-9 w-full max-w-sm border-transparent bg-transparent px-2 text-xl font-semibold md:text-xl tracking-tight shadow-none hover:border-input focus-visible:bg-background sm:w-72 dark:bg-transparent"
      maxLength={80}
      value={name}
      onChange={(e) => setName(e.target.value)}
      onBlur={() =>
        name.trim() &&
        name !== detail.name &&
        patch.mutate({ id: detail.id, body: { name: name.trim() } })
      }
    />
  )
}

export function ViewToggle({ view, setView }: { view: View; setView: (v: View) => void }) {
  const t = useT()
  return (
    <div
      role="group"
      aria-label={t('helpers.view')}
      className="flex gap-0.5 rounded-xl bg-muted p-0.5"
    >
      {(
        [
          ['canvas', Workflow],
          ['steps', ListOrdered],
        ] as const
      ).map(([v, Icon]) => (
        <Button
          key={v}
          variant="ghost"
          size="sm"
          aria-pressed={view === v}
          onClick={() => setView(v)}
          className={`rounded-lg px-3 ${view === v ? 'bg-card text-foreground shadow-sm hover:bg-card dark:hover:bg-card' : 'text-muted-foreground'}`}
        >
          <Icon data-icon="inline-start" />
          {t(`helpers.view.${v}`)}
        </Button>
      ))}
    </div>
  )
}

// new steps drop in the middle column, one under the other: never on top of Start or Result
const place = (n: number) => ({ x: 280, y: 120 + Math.max(n - 2, 0) * 130 })

/** The "Add a step" menu, wired to insert each kind of step. */
export function StepAdder({
  disabled,
  helpers,
  graph,
  setGraph,
  setSelection,
  setRefused,
  setAdding,
}: {
  disabled: boolean
  helpers: Agent[]
  graph: Graph
  setGraph: SetGraph
  setSelection: (s: Selection) => void
  setRefused: (r: Refusal | null) => void
  setAdding: (e: unknown) => void
}) {
  const fetchAgent = useFetchAgent()
  /** Adds a step on top of whatever the graph is *now* (an async lookup may have finished after
   *  other edits), never on the snapshot from when the gesture started. */
  const insert = (id: string, make: (count: number) => GraphNode) => {
    if (graph.nodes.length >= MAX_NODES) {
      setRefused('too_many')
      return
    }
    setRefused(null)
    setGraph((g) => addNode(g, make(g.nodes.length)))
    setSelection({ kind: 'node', id })
  }
  return (
    <AddMenu
      disabled={disabled}
      helpers={helpers}
      onHelper={(id) => {
        // pinned to the version that is current now; "update" in the inspector moves it later
        setAdding(null)
        fetchAgent(id).then((d) => {
          const nid = newId()
          insert(nid, (n) => ({
            type: 'agent',
            id: nid,
            agent_id: d.id,
            agent_version_id: d.version_id,
            position: place(n),
          }))
        }, setAdding)
      }}
      onTool={(tool) => {
        const id = newId()
        insert(id, (n) => ({
          type: 'tool',
          fixed: {},
          id,
          tool,
          position: place(n),
          ...(tool === 'wait' && { minutes: 60 }),
        }))
      }}
      onCondition={() => {
        const id = newId()
        insert(id, (n) => ({
          type: 'condition',
          id,
          op: 'contains',
          value: '',
          position: place(n),
        }))
      }}
      onTransform={() => {
        const id = newId()
        insert(id, (n) => ({ type: 'transform', id, op: 'trim', arg: null, position: place(n) }))
      }}
    />
  )
}

export function LayoutButton({
  disabled,
  setGraph,
  setFit,
}: {
  disabled: boolean
  setGraph: SetGraph
  setFit: Dispatch<SetStateAction<number>>
}) {
  const t = useT()
  return (
    <Button
      variant="ghost"
      size="sm"
      className="text-muted-foreground sm:ml-auto"
      disabled={disabled}
      onClick={() => {
        setGraph((g) => autoLayout(g))
        setFit((n) => n + 1)
      }}
    >
      <LayoutGrid data-icon="inline-start" />
      {t('helpers.layout')}
    </Button>
  )
}

/** Run hint, errors, the save conflict, the live-run lock and a refused gesture. */
export function Notices({
  hint,
  error,
  conflict,
  locked,
  refused,
  onReload,
  onKeep,
}: {
  hint: string
  error: unknown
  conflict: boolean
  locked: boolean
  refused: Refusal | null
  onReload: () => void
  onKeep: () => void
}) {
  const t = useT()
  return (
    <>
      {hint && (
        <p id="run-hint" className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      <ErrorMessage error={conflict ? null : error} />
      {conflict && <ConflictBanner onReload={onReload} onKeep={onKeep} />}
      {locked && (
        <p className="flex items-start gap-2 rounded-xl border bg-muted/50 px-3 py-2 text-sm">
          <Lock aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          {t('helpers.live.locked')}
        </p>
      )}
      {refused && (
        <p
          role="alert"
          className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t(`helpers.refused.${refused}`)}
        </p>
      )}
    </>
  )
}

/** The graph as a canvas or as a list; read-only (with run moods) while a run is shown. */
export function GraphView({
  view,
  graph,
  specs,
  labels,
  live,
  locked,
  selection,
  fit,
  setGraph,
  setSelection,
  setRefused,
}: {
  view: View
  graph: Graph
  specs: Specs
  labels: Labels
  live: {
    moods: ReadonlyMap<string, Mood>
    packets: ReadonlyMap<string, number>
    statusLabels: ReadonlyMap<string, string>
  }
  locked: boolean
  selection: Selection
  fit: number
  setGraph: SetGraph
  setSelection: (s: Selection) => void
  setRefused: (r: Refusal) => void
}) {
  const { titles, avatars } = labels
  const { moods, packets, statusLabels } = live
  return view === 'canvas' ? (
    <Suspense fallback={<ListSkeleton rows={4} />}>
      <Canvas
        graph={graph}
        specs={specs}
        titles={titles}
        avatars={avatars}
        moods={locked ? moods : undefined}
        packets={locked ? packets : undefined}
        statusLabels={locked ? statusLabels : undefined}
        readOnly={locked}
        selection={selection}
        fitSignal={fit}
        onGraph={setGraph}
        onSelect={setSelection}
        onRefuse={setRefused}
      />
    </Suspense>
  ) : (
    <StepsList
      graph={graph}
      specs={specs}
      titles={titles}
      avatars={avatars}
      moods={locked ? moods : undefined}
      readOnly={locked}
      selection={selection}
      onGraph={setGraph}
      onSelect={setSelection}
      onRefuse={setRefused}
    />
  )
}

/** Beside the graph: the run in progress, or the inspector of the selected step or link. */
export function SidePanel({
  locked,
  run,
  saved,
  graph,
  specs,
  labels,
  moods,
  selection,
  setLiveId,
  setGraph,
}: {
  locked: boolean
  run: Run | undefined
  saved: Graph
  graph: Graph
  specs: Specs
  labels: Labels
  moods: ReadonlyMap<string, Mood>
  selection: Selection
  setLiveId: (id: string | null) => void
  setGraph: SetGraph
}) {
  const t = useT()
  const { titles, avatars } = labels
  const selectedNode =
    selection?.kind === 'node' ? graph.nodes.find((n) => n.id === selection.id) : undefined
  if (locked)
    return run ? (
      <LiveRunPanel
        key={run.id}
        run={run}
        graph={saved}
        titles={titles}
        avatars={avatars}
        moods={moods}
        onFollow={setLiveId}
        onClose={() => setLiveId(null)}
      />
    ) : (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner />
        {t('helpers.running')}
      </p>
    )
  return (
    <>
      {selection?.kind === 'edge' && (
        <EdgeInspector
          key={selection.id}
          graph={graph}
          specs={specs}
          edgeId={selection.id}
          titles={titles}
          avatars={avatars}
          onGraph={setGraph}
        />
      )}
      {selectedNode && (
        <NodeInspector
          key={selectedNode.id}
          graph={graph}
          node={selectedNode}
          title={titles.get(selectedNode.id) ?? ''}
          avatar={avatars.get(selectedNode.id)}
          spec={
            selectedNode.type === 'agent' ? specs.get(selectedNode.agent_version_id) : undefined
          }
          onGraph={setGraph}
        />
      )}
    </>
  )
}
