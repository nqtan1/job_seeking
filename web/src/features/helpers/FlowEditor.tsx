import { type Dispatch, type SetStateAction, useMemo, useState } from 'react'
import { useParams } from 'react-router'
import '@/features/helpers/lib'
import { useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import {
  type Agent,
  type FlowDetail,
  type Handoff,
  type Run,
  isLive,
  useAgents,
  useFlow,
  usePatchFlow,
  useRun,
  useSpecs,
  useToolTable,
} from './api'
import { useLabels } from './lib'
import { Details, LeaveGuard } from './ui'
import { DataFlowTable, ValidationPanel } from './FlowPanels'
import type { Graph, Issue, Refusal, Specs } from './graph'
import { RecentRuns } from './RunParts'
import { SchedulePanel } from './Schedules'
import { usePlayback } from './playback'
import type { Selection } from './Canvas'
import { toolText } from '@/features/tools/api'
import { RunDialog } from './RunDialog'
import { useFlowDraft } from './useFlowDraft'
import {
  GraphView,
  LayoutButton,
  NameInput,
  Notices,
  RunActions,
  SidePanel,
  StepAdder,
  type View,
  ViewToggle,
} from './FlowEditorParts'

const NO_HANDOFFS: Handoff[] = []
const initialView = (): View =>
  window.matchMedia?.('(min-width: 1024px)').matches ? 'canvas' : 'steps'

export function FlowEditor() {
  const t = useT()
  const { flowId } = useParams()
  const flow = useFlow(flowId)
  const tools = useToolTable() // the ports of every action step
  if (flow.data && tools.data) return <Editor key={flow.data.id} detail={flow.data} />
  return (
    <Page
      title={t('helpers.flow.title')}
      back={{ to: '/automations', label: t('helpers.back_flows') }}
      wide
    >
      {flow.error || tools.error ? (
        <ErrorMessage error={flow.error ?? tools.error} />
      ) : (
        <ListSkeleton />
      )}
    </Page>
  )
}

function Editor({ detail }: { detail: FlowDetail }) {
  const t = useT()
  const draft = useFlowDraft(detail)
  const { graph, setGraph, saved, dirty, add } = draft
  const [view, setView] = useState<View>(initialView)
  const [selection, setSelection] = useState<Selection>(null)
  const [refused, setRefused] = useState<Refusal | null>(null)
  const runDialog = useRunDialog()
  const [fit, setFit] = useState(0)
  const [liveId, setLiveId] = useState<string | null>(null) // the run shown in place, if any
  const [adding, setAdding] = useState<unknown>(null)
  const agents = useAgents()
  const { specs } = useSpecs(graph)
  const labels = useTitles(graph, agents.data)
  const patch = usePatchFlow()
  const { live, ...playback } = useLiveRun(liveId)

  const locked = liveId !== null // editing waits while a run is on screen
  const { canRun, hint } = runGate(t, draft, live)

  return (
    <Page
      title={t('helpers.flow.title')}
      back={{ to: '/automations', label: t('helpers.back_flows') }}
      wide
      actions={
        <RunActions
          dirty={dirty}
          base={draft.base}
          saving={add.isPending}
          canRun={canRun}
          hint={hint}
          onSave={draft.save}
          onRun={runDialog.open}
        />
      }
    >
      <div className="space-y-4">
        <Toolbar
          detail={detail}
          patch={patch}
          view={view}
          setView={setView}
          locked={locked}
          agents={agents.data}
          graph={graph}
          setGraph={setGraph}
          setSelection={setSelection}
          setRefused={setRefused}
          setAdding={setAdding}
          setFit={setFit}
        />
        <Notices
          hint={hint}
          error={add.error ?? patch.error ?? adding}
          conflict={draft.conflict}
          locked={locked}
          refused={refused}
          onReload={draft.reload}
          onKeep={draft.keepMine}
        />

        <Workspace
          flow={detail}
          issues={draft.issues}
          dirty={dirty}
          view={view}
          graph={graph}
          saved={saved}
          specs={specs}
          labels={labels}
          run={live}
          playback={playback}
          locked={locked}
          selection={selection}
          fit={fit}
          setGraph={setGraph}
          setSelection={setSelection}
          setRefused={setRefused}
          setLiveId={setLiveId}
        />

        <RunDialog
          key={runDialog.key}
          open={runDialog.running}
          flow={detail}
          graph={saved}
          specs={specs}
          onStarted={(id) => {
            runDialog.close()
            setSelection(null)
            setLiveId(id)
          }}
          onClose={runDialog.close}
        />
        <LeaveGuard dirty={dirty} leaving={draft.leaving} />
      </div>
    </Page>
  )
}

/** Step titles (tool steps named by their tool) and helper avatars. */
function useTitles(graph: Graph, agents: Agent[] | undefined) {
  const t = useT()
  const labels = useLabels(graph, agents)
  const { avatars } = labels
  const titles = useMemo(() => {
    const m = new Map(labels.titles)
    for (const n of graph.nodes) {
      if (n.type === 'tool') m.set(n.id, toolText(t, n.tool, 'name'))
    }
    return m
  }, [labels.titles, graph.nodes, t])
  return { titles, avatars }
}

/** The run shown in place of the editor, played back step by step. */
function useLiveRun(liveId: string | null) {
  const t = useT()
  const live = useRun(liveId ?? undefined).data
  const { moods, packets } = usePlayback(live?.steps, live?.handoffs ?? NO_HANDOFFS)
  const statusLabels = useMemo(
    () => new Map((live?.steps ?? []).map((s) => [s.node_id, t(`helpers.run.status.${s.status}`)])),
    [live?.steps, t],
  )
  return { live, moods, packets, statusLabels }
}

/** The graph (canvas or list) with its data-flow table and recent runs, and the side panel. */
function Workspace({
  flow,
  issues,
  dirty,
  view,
  graph,
  saved,
  specs,
  labels,
  run,
  playback,
  locked,
  selection,
  fit,
  setGraph,
  setSelection,
  setRefused,
  setLiveId,
}: {
  flow: FlowDetail
  issues: Issue[] | undefined
  dirty: boolean
  view: View
  graph: Graph
  saved: Graph
  specs: Specs
  labels: ReturnType<typeof useTitles>
  run: Run | undefined
  playback: Omit<ReturnType<typeof useLiveRun>, 'live'>
  locked: boolean
  selection: Selection
  fit: number
  setGraph: Dispatch<SetStateAction<Graph>>
  setSelection: (s: Selection) => void
  setRefused: (r: Refusal) => void
  setLiveId: (id: string | null) => void
}) {
  return (
    <>
      {!locked && (
        <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
          <ValidationPanel titles={labels.titles} issues={issues} onJump={setSelection} />
          <SchedulePanel flow={flow} graph={saved} specs={specs} dirty={dirty} />
        </div>
      )}
      <div
        className={
          locked || selection ? 'grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]' : 'grid gap-4'
        }
      >
        <div className="min-w-0 space-y-4">
          <GraphView
            view={view}
            graph={graph}
            specs={specs}
            labels={labels}
            live={playback}
            locked={locked}
            selection={selection}
            fit={fit}
            setGraph={setGraph}
            setSelection={setSelection}
            setRefused={setRefused}
          />
          <Details>
            <DataFlowTable
              graph={graph}
              titles={labels.titles}
              avatars={labels.avatars}
              handoffs={run?.handoffs}
              onSelect={setSelection}
            />
            <RecentRuns flowId={flow.id} />
          </Details>
        </div>
        {(locked || selection) && (
          <div className={`space-y-4 ${locked ? 'order-first lg:order-none' : ''}`}>
            <SidePanel
              locked={locked}
              run={run}
              saved={saved}
              graph={graph}
              specs={specs}
              labels={labels}
              moods={playback.moods}
              selection={selection}
              setLiveId={setLiveId}
              setGraph={setGraph}
            />
          </div>
        )}
      </div>
    </>
  )
}

/** Run waits for a saved, valid flow and no run already going. */
function runGate(
  t: ReturnType<typeof useT>,
  draft: ReturnType<typeof useFlowDraft>,
  live: Run | undefined,
) {
  const { dirty, add } = draft
  const errors = (draft.issues ?? []).filter((i) => i.severity === 'error').length
  const canRun = !dirty && errors === 0 && !add.isPending && !(live && isLive(live.status))
  const hint = canRun
    ? ''
    : dirty
      ? t('helpers.run_save_first')
      : errors
        ? t('helpers.run_fix_first')
        : ''
  return { canRun, hint }
}

/** A fresh run dialog (and idempotency key) per opening. */
function useRunDialog() {
  const [running, setRunning] = useState(false)
  const [key, setKey] = useState(0)
  const open = () => {
    setKey((k) => k + 1)
    setRunning(true)
  }
  return { running, key, open, close: () => setRunning(false) }
}

/** Name, view switch, "Add a step" and auto-arrange. */
function Toolbar({
  detail,
  patch,
  view,
  setView,
  locked,
  agents,
  graph,
  setGraph,
  setSelection,
  setRefused,
  setAdding,
  setFit,
}: {
  detail: FlowDetail
  patch: ReturnType<typeof usePatchFlow>
  view: View
  setView: (v: View) => void
  locked: boolean
  agents: Agent[] | undefined
  graph: Graph
  setGraph: Dispatch<SetStateAction<Graph>>
  setSelection: (s: Selection) => void
  setRefused: (r: Refusal | null) => void
  setAdding: (e: unknown) => void
  setFit: Dispatch<SetStateAction<number>>
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <NameInput detail={detail} patch={patch} />
      <ViewToggle view={view} setView={setView} />
      <StepAdder
        disabled={locked}
        helpers={(agents ?? []).filter((a) => !a.archived)}
        graph={graph}
        setGraph={setGraph}
        setSelection={setSelection}
        setRefused={setRefused}
        setAdding={setAdding}
      />
      {view === 'canvas' && <LayoutButton disabled={locked} setGraph={setGraph} setFit={setFit} />}
    </div>
  )
}
