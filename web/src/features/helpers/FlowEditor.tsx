import {
  CircleCheck,
  LayoutGrid,
  ListOrdered,
  Lock,
  Play,
  Plus,
  Save,
  Sparkles,
  Workflow,
} from 'lucide-react'
import { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router'
import '@/features/helpers/lib'
import { useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Spinner } from '@/components/Spinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { toast } from '@/lib/toast'
import {
  type FlowDetail,
  type Handoff,
  isConflict,
  isLive,
  useAddFlowVersion,
  useAgents,
  useFetchAgent,
  useFetchFlow,
  useFlow,
  usePatchFlow,
  useRun,
  useSpecs,
  useStartRun,
  useValidate,
} from './api'
import { clearDraft, loadDraft, saveDraft, useLabels } from './lib'
import { ConflictBanner, Details, JobSelect, LeaveGuard } from './ui'
import { DataFlowTable, EdgeInspector, NodeInspector, ValidationPanel } from './FlowPanels'
import {
  type Graph,
  type GraphNode,
  type Issue,
  MAX_INPUT_CHARS,
  MAX_NODES,
  type Refusal,
  TOOL_KINDS,
  type Specs,
  addNode,
  aiCalls,
  autoLayout,
  newId,
  typeKey,
} from './graph'
import { LiveRunPanel, RecentRuns } from './RunParts'
import { SchedulePanel } from './Schedules'
import { usePlayback } from './playback'
import { StepsList } from './StepsList'
import type { Selection } from './Canvas'
import { Modal } from '@/components/Modal'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useAiUse } from '@/features/radar/api'

const Canvas = lazy(() => import('./Canvas')) // React Flow is large: only this page pays for it
const NO_HANDOFFS: Handoff[] = []
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

export function FlowEditor() {
  const t = useT()
  const { flowId } = useParams()
  const flow = useFlow(flowId)
  if (flow.data) return <Editor key={flow.data.id} detail={flow.data} />
  return (
    <Page
      title={t('helpers.flow.title')}
      back={{ to: '/automations', label: t('helpers.back_flows') }}
      wide
    >
      {flow.error ? <ErrorMessage error={flow.error} /> : <ListSkeleton />}
    </Page>
  )
}

function Editor({ detail }: { detail: FlowDetail }) {
  const t = useT()
  const key = `flow-draft:${detail.id}`
  const [graph, setGraph] = useState<Graph>(() => {
    const kept = loadDraft<{ base: number; graph: Graph }>(key)
    return kept && kept.base === detail.current_version && !same(kept.graph, detail.graph)
      ? kept.graph
      : detail.graph
  })
  const [base, setBase] = useState(detail.current_version)
  const [saved, setSaved] = useState<Graph>(detail.graph)
  const [view, setView] = useState<'canvas' | 'steps'>(() =>
    window.matchMedia?.('(min-width: 1024px)').matches ? 'canvas' : 'steps',
  )
  const [selection, setSelection] = useState<Selection>(null)
  const [issues, setIssues] = useState<Issue[] | undefined>(detail.issues)
  const [refused, setRefused] = useState<Refusal | null>(null)
  const [conflict, setConflict] = useState(false)
  const [running, setRunning] = useState(false)
  const [runKey, setRunKey] = useState(0) // a fresh run dialog (and idempotency key) per opening
  const [name, setName] = useState(detail.name)
  const [fit, setFit] = useState(0)
  const [liveId, setLiveId] = useState<string | null>(null) // the run shown in place, if any

  const agents = useAgents()
  const { specs } = useSpecs(graph)
  const labels = useLabels(graph, agents.data)
  const { avatars } = labels
  // the transform step is "Clean text" to people; the shared labels still say "Tidy text"
  const titles = useMemo(() => {
    const m = new Map(labels.titles)
    for (const n of graph.nodes) {
      if (n.type === 'transform') m.set(n.id, t(typeKey(n.type)))
      if (n.type === 'tool') m.set(n.id, t(`helpers.tool.${n.tool}.name`))
    }
    return m
  }, [labels.titles, graph.nodes, t])
  const add = useAddFlowVersion()
  const patch = usePatchFlow()
  const { mutate: checkGraph } = useValidate()
  const fetchAgent = useFetchAgent()
  const fetchFlow = useFetchFlow()
  const [adding, setAdding] = useState<unknown>(null)

  const dirty = !same(graph, saved)
  useEffect(() => {
    if (dirty) saveDraft(key, { base, graph })
    else clearDraft(key)
  }, [dirty, graph, base, key])
  const leaving = useRef(false) // raised just before a deliberate reload

  // The server is the only judge: ask after a pause, keep only the newest answer.
  const ask = useRef(0)
  useEffect(() => {
    const mine = ++ask.current
    const id = setTimeout(() => {
      checkGraph(graph, {
        onSuccess: (r) => {
          if (mine === ask.current) setIssues(r.issues)
        },
      })
    }, 500)
    return () => clearTimeout(id)
    // `validate` is a stable mutation object; the graph is the input
  }, [graph, checkGraph])

  const save = async () => {
    setConflict(false)
    try {
      const v = await add.mutateAsync({ id: detail.id, basedOn: base, graph })
      setBase(v.version)
      setSaved(graph)
      clearDraft(key)
      toast(t('helpers.saved'))
    } catch (e) {
      if (isConflict(e)) setConflict(true)
    }
  }

  // new steps drop in the middle column, one under the other: never on top of Start or Result
  const place = (n: number) => ({ x: 280, y: 120 + Math.max(n - 2, 0) * 130 })
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
  const pickable = (agents.data ?? []).filter((a) => !a.archived)

  const errors = (issues ?? []).filter((i) => i.severity === 'error').length
  const selectedNode =
    selection?.kind === 'node' ? graph.nodes.find((n) => n.id === selection.id) : undefined
  const live = useRun(liveId ?? undefined).data
  const { moods, packets } = usePlayback(live?.steps, live?.handoffs ?? NO_HANDOFFS)
  const statusLabels = useMemo(
    () => new Map((live?.steps ?? []).map((s) => [s.node_id, t(`helpers.step.${s.status}`)])),
    [live?.steps, t],
  )
  const locked = liveId !== null // editing waits while a run is on screen
  const canRun = !dirty && errors === 0 && !add.isPending && !(live && isLive(live.status))

  const hint = canRun
    ? ''
    : dirty
      ? t('helpers.run_save_first')
      : errors
        ? t('helpers.run_fix_first')
        : ''

  return (
    <Page
      title={t('helpers.flow.title')}
      back={{ to: '/automations', label: t('helpers.back_flows') }}
      wide
      actions={
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
          <Button variant="outline" onClick={save} disabled={!dirty || add.isPending}>
            {add.isPending ? <Spinner /> : <Save data-icon="inline-start" />}
            {t('helpers.save_version')} · v{base}
          </Button>
          <Button
            onClick={() => {
              setRunKey((k) => k + 1)
              setRunning(true)
            }}
            disabled={!canRun}
            title={canRun ? undefined : t('helpers.run_disabled')}
            aria-describedby={hint ? 'run-hint' : undefined}
          >
            <Play data-icon="inline-start" />
            {t('helpers.run_flow')}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
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
          <AddMenu
            disabled={locked}
            helpers={pickable}
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
              insert(id, (n) => ({
                type: 'transform',
                id,
                op: 'trim',
                arg: null,
                position: place(n),
              }))
            }}
          />
          {view === 'canvas' && (
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground sm:ml-auto"
              disabled={locked}
              onClick={() => {
                setGraph((g) => autoLayout(g))
                setFit((n) => n + 1)
              }}
            >
              <LayoutGrid data-icon="inline-start" />
              {t('helpers.layout')}
            </Button>
          )}
        </div>
        {hint && (
          <p id="run-hint" className="text-xs text-muted-foreground">
            {hint}
          </p>
        )}
        <ErrorMessage error={conflict ? null : (add.error ?? patch.error ?? adding)} />
        {conflict && (
          <ConflictBanner
            onReload={() => {
              clearDraft(key)
              leaving.current = true // a deliberate reload must not ask again
              window.location.reload()
            }}
            onKeep={async () => {
              // build on what the server has now, so the next save is not refused again
              const fresh = await fetchFlow(detail.id)
              setBase(fresh.current_version)
              setConflict(false)
            }}
          />
        )}
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

        {!locked && (
          <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
            <ValidationPanel titles={titles} issues={issues} onJump={setSelection} />
            <SchedulePanel flow={detail} graph={saved} specs={specs} dirty={dirty} />
          </div>
        )}

        <div
          className={
            locked || selection ? 'grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]' : 'grid gap-4'
          }
        >
          <div className="min-w-0 space-y-4">
            {view === 'canvas' ? (
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
            )}
            <Details>
              <DataFlowTable
                graph={graph}
                titles={titles}
                avatars={avatars}
                handoffs={live?.handoffs}
                onSelect={setSelection}
              />
              <RecentRuns flowId={detail.id} />
            </Details>
          </div>
          {(locked || selection) && (
            <div className={`space-y-4 ${locked ? 'order-first lg:order-none' : ''}`}>
              {locked ? (
                <>
                  {live ? (
                    <LiveRunPanel
                      key={live.id}
                      run={live}
                      graph={saved}
                      titles={titles}
                      avatars={avatars}
                      moods={moods}
                      onFollow={setLiveId}
                      onClose={() => setLiveId(null)}
                    />
                  ) : (
                    <p
                      role="status"
                      className="flex items-center gap-2 text-sm text-muted-foreground"
                    >
                      <Spinner />
                      {t('helpers.ui.working')}
                    </p>
                  )}
                </>
              ) : (
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
                        selectedNode.type === 'agent'
                          ? specs.get(selectedNode.agent_version_id)
                          : undefined
                      }
                      onGraph={setGraph}
                    />
                  )}
                </>
              )}
            </div>
          )}
        </div>

        <RunDialog
          key={runKey}
          open={running}
          flow={detail}
          graph={saved}
          specs={specs}
          onStarted={(id) => {
            setRunning(false)
            setSelection(null)
            setLiveId(id)
          }}
          onClose={() => setRunning(false)}
        />
        <LeaveGuard dirty={dirty} leaving={leaving} />
      </div>
    </Page>
  )
}

/** Inputs, a job when a helper needs one, and the price before it starts: "up to N of your M". */
function RunDialog({
  open,
  flow,
  graph,
  specs,
  onStarted,
  onClose,
}: {
  open: boolean
  flow: FlowDetail
  graph: Graph
  specs: Specs
  onStarted: (runId: string) => void
  onClose: () => void
}) {
  const t = useT()
  const start = useStartRun()
  const use = useAiUse()
  const [values, setValues] = useState<Record<string, string>>({})
  const [jobId, setJobId] = useState('')
  // The idempotency key belongs to one exact request: a double click or a retry after a lost
  // response reuses it (one run), while editing the inputs starts a new request (a new key).
  const attempt = useRef({ sig: '', key: '' })
  const keyFor = (sig: string) => {
    if (attempt.current.sig !== sig) attempt.current = { sig, key: crypto.randomUUID() }
    return attempt.current.key
  }

  const input = graph.nodes.find((n) => n.type === 'input')
  const fields = input?.type === 'input' ? input.fields : []
  const needsJob = graph.nodes.some(
    (n) =>
      (n.type === 'tool' && (n.tool === 'job_lookup' || n.tool === 'fit_check')) ||
      (n.type === 'agent' &&
        (specs.get(n.agent_version_id)?.context_sources ?? []).some(
          (s) => s === 'job' || s === 'fit',
        )),
  )
  const need = aiCalls(graph)
  const left = use.data ? Math.max(use.data.quota - use.data.used, 0) : null
  const missing =
    fields.some((f) => (f.required ?? true) && !(values[f.name] ?? '').trim()) ||
    (needsJob && !jobId)
  const tooMany = left !== null && need > left

  return (
    <Modal open={open} label={t('helpers.run_flow')} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          start.mutate(
            {
              id: flow.id,
              inputs: values,
              jobId: jobId || null,
              key: keyFor(JSON.stringify([values, jobId])),
            },
            { onSuccess: (run) => onStarted(run.id) },
          )
        }}
      >
        <h2 className="text-lg font-semibold tracking-tight">{flow.name}</h2>
        {fields.map((f) => (
          <div key={f.name} className="space-y-1.5">
            <Label htmlFor={`run-${f.name}`}>{f.label}</Label>
            <Textarea
              id={`run-${f.name}`}
              rows={3}
              maxLength={MAX_INPUT_CHARS}
              value={values[f.name] ?? ''}
              onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
            />
          </div>
        ))}
        {needsJob && <JobSelect id="run-job" value={jobId} onChange={setJobId} />}
        <p
          className={`flex items-start gap-2 rounded-xl border px-3 py-2.5 text-sm ${tooMany ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'bg-muted/50 text-muted-foreground'}`}
        >
          <Sparkles aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>
            {left === null
              ? t('helpers.flow.cost', { count: need })
              : t('helpers.run.price', { need, left })}
          </span>
        </p>
        <ErrorMessage error={start.error} />
        <div className="flex justify-end gap-2 border-t pt-4">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('helpers.cancel')}
          </Button>
          <Button type="submit" disabled={missing || start.isPending || tooMany}>
            {start.isPending ? <Spinner /> : <Play data-icon="inline-start" />}
            {t('helpers.live.watch')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/** The one "+ Add" menu: a helper, an action, a condition or a clean-text step. */
function AddMenu({
  disabled,
  helpers,
  onHelper,
  onTool,
  onCondition,
  onTransform,
}: {
  disabled: boolean
  helpers: { id: string; name: string }[]
  onHelper: (id: string) => void
  onTool: (tool: (typeof TOOL_KINDS)[number]) => void
  onCondition: () => void
  onTransform: () => void
}) {
  const t = useT()
  const ref = useRef<HTMLDetailsElement>(null)
  const item =
    'block w-full rounded-lg px-2 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50'
  const head = 'px-2 pt-2 pb-1 text-xs font-medium text-muted-foreground'
  const pick = (f: () => void) => () => {
    if (ref.current) ref.current.open = false
    f()
  }
  if (disabled)
    return (
      <Button size="sm" disabled>
        <Plus data-icon="inline-start" />
        {t('helpers.flow.add')}
      </Button>
    )
  return (
    <details
      ref={ref}
      className="relative"
      onKeyDown={(e) => e.key === 'Escape' && ref.current && (ref.current.open = false)}
    >
      <summary className="inline-flex h-7 cursor-pointer list-none items-center gap-1 rounded-lg border bg-background px-2.5 text-sm font-medium outline-none select-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 pointer-coarse:h-11 [&::-webkit-details-marker]:hidden">
        <Plus aria-hidden className="size-4" />
        {t('helpers.flow.add')}
      </summary>
      <div className="absolute top-full left-0 z-20 mt-1 max-h-96 w-60 overflow-y-auto rounded-xl border bg-popover p-1 shadow-lg">
        {helpers.length > 0 && (
          <>
            <p className={head}>{t('helpers.node.agent')}</p>
            {helpers.map((a) => (
              <button
                key={a.id}
                type="button"
                className={item}
                onClick={pick(() => onHelper(a.id))}
              >
                {a.name}
              </button>
            ))}
          </>
        )}
        <p className={head}>{t('helpers.node.tool')}</p>
        {TOOL_KINDS.map((k) => (
          <button key={k} type="button" className={item} onClick={pick(() => onTool(k))}>
            {t(`helpers.tool.${k}.name`)}
          </button>
        ))}
        <button type="button" className={item} onClick={pick(onCondition)}>
          {t('helpers.node.condition')}
        </button>
        <button type="button" className={item} onClick={pick(onTransform)}>
          {t(typeKey('transform'))}
        </button>
      </div>
    </details>
  )
}
