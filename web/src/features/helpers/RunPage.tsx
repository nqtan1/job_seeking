import '@/features/helpers/lib'
import { Ban, ChevronRight, Pause, Play, RotateCcw } from 'lucide-react'
import {
  type Dispatch,
  type SetStateAction,
  Suspense,
  lazy,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { useParams } from 'react-router'
import { cn } from 'cn'
import { useI18n, useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Spinner } from '@/components/Spinner'
import { Button } from '@/components/ui/button'
import { replayFrames, useErrText, usePlayback } from './playback'
import {
  type Run,
  isLive,
  useAgents,
  useCancelRun,
  useFlowVersions,
  useResumeRun,
  useRun,
  useSpecs,
  useToolTable,
} from './api'
import { DataFlowTable, EdgeInspector } from './FlowPanels'
import { type Graph, orderOf } from './graph'
import { useLabels, when } from './lib'
import { ResultHero, RunSummary, StepTimeline } from './RunParts'
import { StepsList } from './StepsList'
import { Details } from './ui'
import type { Selection } from './Canvas'

const Canvas = lazy(() => import('./Canvas'))

export function RunPage() {
  const t = useT()
  const { runId } = useParams()
  const run = useRun(runId)
  const tools = useToolTable()
  return (
    <Page title={t('helpers.run')} back={{ to: '/activity', label: t('nav.activity') }} wide>
      {run.data && tools.data ? (
        <View run={run.data} />
      ) : run.error || tools.error ? (
        <ErrorMessage error={run.error ?? tools.error} />
      ) : (
        <ListSkeleton />
      )}
    </Page>
  )
}

type Labels = ReturnType<typeof useLabels>
type Moods = ReturnType<typeof usePlayback>['moods']
type Packets = ReturnType<typeof usePlayback>['packets']
type ReplayState = { i: number; playing: boolean; status: string }

function useReplay(run: Run, graph: Graph | undefined, moods: Moods) {
  // Replay position. It belongs to one run status: when the run changes under it (a resume, say)
  // the replay is dropped instead of pointing at frames that no longer exist.
  const [replayState, setReplay] = useState<ReplayState | null>(null)
  const replay = replayState?.status === run.status ? replayState : null
  const frame = replay?.i ?? null
  const frames = useMemo(() => replayFrames(run.steps), [run.steps])
  const calm = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
  const playing = replay?.playing === true

  useEffect(() => {
    if (!playing) return
    const id = setInterval(
      () => setReplay((r) => r && (r.i + 1 >= frames.length ? null : { ...r, i: r.i + 1 })),
      calm ? 200 : 800,
    )
    return () => clearInterval(id)
  }, [playing, frames.length, calm])

  const shown = frame === null ? moods : frames[frame]
  const replayPackets = useMemo(() => {
    if (frame === null || !graph || calm) return undefined
    const node = [...run.steps].sort((a, b) => a.position - b.position)[frame]?.node_id
    return new Map(
      run.handoffs.filter((h) => h.to_node === node).map((h) => [h.edge_id, frame + 1]),
    )
  }, [frame, graph, calm, run.steps, run.handoffs])
  return { replay, setReplay, frame, frames, playing, shown, replayPackets }
}

function RunHeader({
  run,
  live,
  stepFailed,
  resume,
  cancel,
  errText,
}: {
  run: Run
  live: boolean
  stepFailed: boolean
  resume: ReturnType<typeof useResumeRun>
  cancel: ReturnType<typeof useCancelRun>
  errText: ReturnType<typeof useErrText>
}) {
  const { t, locale } = useI18n()
  const actions = (
    <>
      {live && (
        <Button
          variant="outline"
          size="sm"
          disabled={cancel.isPending}
          onClick={() => cancel.mutate(run.id)}
        >
          <Ban data-icon="inline-start" />
          {t('helpers.run.cancel')}
        </Button>
      )}
      {run.status === 'failed' && !stepFailed && (
        <Button size="sm" disabled={resume.isPending} onClick={() => resume.mutate(run.id)}>
          {resume.isPending ? <Spinner /> : <RotateCcw data-icon="inline-start" />}
          {t('helpers.run.resume')}
        </Button>
      )}
    </>
  )
  return (
    <>
      <RunSummary run={run} live={live} actions={actions} />
      <ErrorMessage error={resume.error ?? cancel.error} />
      {run.status === 'failed' && run.error_code && !stepFailed && (
        <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {errText(run.error_code)}
        </p>
      )}
      <div role="status" className="sr-only" aria-live="polite">
        {t(`helpers.run.status.${run.status}`)}
      </div>
      {run.status === 'waiting' && (
        <p className="text-sm text-muted-foreground">
          {t('helpers.run.waiting_until', { time: when(run.wake_at, locale) })}
        </p>
      )}
      <ResultHero run={run} />
      {live && !run.result && (
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner />
          {t('helpers.running')}
        </p>
      )}
    </>
  )
}

function ReplayControls({
  run,
  live,
  replay,
  setReplay,
  frame,
  frameCount,
  playing,
}: {
  run: Run
  live: boolean
  replay: ReplayState | null
  setReplay: (r: ReplayState) => void
  frame: number | null
  frameCount: number
  playing: boolean
}) {
  const t = useT()
  return (
    <>
      {!live && run.steps.length > 0 && (
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            setReplay(
              playing && replay
                ? { ...replay, playing: false }
                : { i: 0, playing: true, status: run.status },
            )
          }
          aria-pressed={playing}
        >
          {playing ? <Pause data-icon="inline-start" /> : <Play data-icon="inline-start" />}
          {t('helpers.replay')}
        </Button>
      )}
      {frame !== null && (
        <input
          type="range"
          min={0}
          max={Math.max(frameCount - 1, 0)}
          value={frame}
          aria-label={t('helpers.replay')}
          onChange={(e) =>
            setReplay({ i: Number(e.target.value), playing: false, status: run.status })
          }
          className="w-full"
        />
      )}
    </>
  )
}

function MapToolbar({
  mapOpen,
  setMapOpen,
  view,
  setView,
}: {
  mapOpen: boolean
  setMapOpen: Dispatch<SetStateAction<boolean>>
  view: 'canvas' | 'steps'
  setView: (v: 'canvas' | 'steps') => void
}) {
  const t = useT()
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        variant="ghost"
        size="sm"
        aria-expanded={mapOpen}
        onClick={() => setMapOpen((o) => !o)}
        className="-ml-1 text-base font-semibold"
      >
        <ChevronRight
          data-icon="inline-start"
          className={cn('transition-transform duration-200', mapOpen && 'rotate-90')}
        />
        {t('helpers.ui.map')}
      </Button>
      <span className="flex-1" />
      <div role="group" aria-label={t('helpers.view')} className="flex gap-1">
        {(['canvas', 'steps'] as const).map((v) => (
          <Button
            key={v}
            size="sm"
            variant={view === v ? 'default' : 'outline'}
            aria-pressed={view === v}
            onClick={() => {
              setView(v)
              setMapOpen(true)
            }}
          >
            {t(`helpers.view.${v}`)}
          </Button>
        ))}
      </div>
    </div>
  )
}

function MapSection({
  run,
  graph,
  specs,
  titles,
  avatars,
  moods,
  packets,
  selection,
  onSelect,
}: {
  run: Run
  graph: Graph
  specs: ReturnType<typeof useSpecs>['specs']
  titles: Labels['titles']
  avatars: Labels['avatars']
  moods: Moods
  packets: Packets
  selection: Selection
  onSelect: (s: Selection) => void
}) {
  const t = useT()
  const desktop = window.matchMedia?.('(min-width: 1024px)').matches === true
  const [mapOpen, setMapOpen] = useState(desktop)
  const [view, setView] = useState<'canvas' | 'steps'>(() =>
    window.matchMedia?.('(min-width: 1024px)').matches ? 'canvas' : 'steps',
  )
  const statusLabels = useMemo(
    () => new Map(run.steps.map((s) => [s.node_id, t(`helpers.run.status.${s.status}`)])),
    [run.steps, t],
  )
  const common = { graph, specs, titles, avatars, moods, selection, readOnly: true, onSelect }
  return (
    <section className="space-y-3">
      <MapToolbar mapOpen={mapOpen} setMapOpen={setMapOpen} view={view} setView={setView} />
      {mapOpen &&
        (view === 'steps' ? (
          <StepsList {...common} />
        ) : (
          <Suspense fallback={<ListSkeleton rows={4} />}>
            <Canvas {...common} packets={packets} statusLabels={statusLabels} />
          </Suspense>
        ))}
      {selection?.kind === 'edge' && (
        <EdgeInspector
          key={selection.id}
          graph={graph}
          specs={specs}
          edgeId={selection.id}
          titles={titles}
          avatars={avatars}
          readOnly
          actual={run.handoffs.find((h) => h.edge_id === selection.id)}
        />
      )}
    </section>
  )
}

function View({ run }: { run: Run }) {
  const t = useT()
  const versions = useFlowVersions(run.flow_id)
  const found = versions.data?.find((v) => v.id === run.flow_version_id)?.graph
  const graph: Graph | undefined = found
  const agents = useAgents()
  const { specs } = useSpecs(graph)
  const { titles, avatars } = useLabels(graph, agents.data)
  const resume = useResumeRun()
  const cancel = useCancelRun()
  const live = isLive(run.status)
  const { moods, packets } = usePlayback(run.steps, run.handoffs)
  const [selection, setSelection] = useState<Selection>(null)
  const r = useReplay(run, graph, moods)
  const errText = useErrText()
  const stepOf = useMemo(() => new Map(run.steps.map((s) => [s.node_id, s])), [run.steps])
  const stepFailed = run.steps.some((s) => s.status === 'failed')

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <RunHeader
        run={run}
        live={live}
        stepFailed={stepFailed}
        resume={resume}
        cancel={cancel}
        errText={errText}
      />

      {!graph ? (
        <ListSkeleton rows={3} />
      ) : (
        <Details defaultOpen={run.status === 'failed'}>
          <ReplayControls
            run={run}
            live={live}
            replay={r.replay}
            setReplay={r.setReplay}
            frame={r.frame}
            frameCount={r.frames.length}
            playing={r.playing}
          />

          <section className="space-y-3">
            <h2 className="text-base font-semibold tracking-tight">{t('helpers.view.steps')}</h2>
            <StepTimeline
              order={orderOf(graph)}
              steps={stepOf}
              graph={graph}
              titles={titles}
              avatars={avatars}
              moods={r.shown}
              handoffs={run.handoffs}
              errText={errText}
              canResume={run.status === 'failed'}
              resuming={resume.isPending}
              onResume={() => resume.mutate(run.id)}
            />
          </section>

          <MapSection
            run={run}
            graph={graph}
            specs={specs}
            titles={titles}
            avatars={avatars}
            moods={r.shown}
            packets={r.replayPackets ?? packets}
            selection={selection}
            onSelect={setSelection}
          />
          <DataFlowTable
            graph={graph}
            titles={titles}
            avatars={avatars}
            handoffs={run.handoffs}
            onSelect={setSelection}
          />
        </Details>
      )}
    </div>
  )
}
