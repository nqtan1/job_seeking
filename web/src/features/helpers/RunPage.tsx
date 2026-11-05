import '@/features/helpers/lib'
import { Ban, ChevronRight, Pause, Play, RotateCcw } from 'lucide-react'
import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
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
  return (
    <Page
      title={t('helpers.run.title')}
      back={{ to: '/automations?tab=runs', label: t('helpers.back_flows') }}
      wide
    >
      {run.isPending ? (
        <ListSkeleton />
      ) : run.error ? (
        <ErrorMessage error={run.error} />
      ) : (
        <View run={run.data} />
      )}
    </Page>
  )
}

function View({ run }: { run: Run }) {
  const { t, locale } = useI18n()
  const versions = useFlowVersions(run.flow_id)
  const graph: Graph | undefined = versions.data?.find((v) => v.id === run.flow_version_id)?.graph
  const agents = useAgents()
  const { specs } = useSpecs(graph)
  const { titles, avatars } = useLabels(graph, agents.data)
  const resume = useResumeRun()
  const cancel = useCancelRun()
  const live = isLive(run.status)
  const { moods, packets } = usePlayback(run.steps, run.handoffs)
  const [selection, setSelection] = useState<Selection>(null)
  const desktop = window.matchMedia?.('(min-width: 1024px)').matches === true
  const [mapOpen, setMapOpen] = useState(desktop)
  const [view, setView] = useState<'canvas' | 'steps'>(() =>
    window.matchMedia?.('(min-width: 1024px)').matches ? 'canvas' : 'steps',
  )
  // Replay position. It belongs to one run status: when the run changes under it (a resume, say)
  // the replay is dropped instead of pointing at frames that no longer exist.
  const [replayState, setReplay] = useState<{ i: number; playing: boolean; status: string } | null>(
    null,
  )
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

  const errText = useErrText()

  const shown = frame === null ? moods : frames[frame]
  const stepOf = useMemo(() => new Map(run.steps.map((s) => [s.node_id, s])), [run.steps])
  const statusLabels = useMemo(
    () => new Map(run.steps.map((s) => [s.node_id, t(`helpers.step.${s.status}`)])),
    [run.steps, t],
  )
  const replayPackets = useMemo(() => {
    if (frame === null || !graph || calm) return undefined
    const node = [...run.steps].sort((a, b) => a.position - b.position)[frame]?.node_id
    return new Map(
      run.handoffs.filter((h) => h.to_node === node).map((h) => [h.edge_id, frame + 1]),
    )
  }, [frame, graph, calm, run.steps, run.handoffs])

  const stepFailed = run.steps.some((s) => s.status === 'failed')
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
    <div className="mx-auto max-w-4xl space-y-5">
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
          {t('helpers.ui.working')}
        </p>
      )}

      {!graph ? (
        <ListSkeleton rows={3} />
      ) : (
        <Details defaultOpen={run.status === 'failed'}>
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
              max={Math.max(frames.length - 1, 0)}
              value={frame}
              aria-label={t('helpers.replay')}
              onChange={(e) =>
                setReplay({ i: Number(e.target.value), playing: false, status: run.status })
              }
              className="w-full"
            />
          )}

          <section className="space-y-3">
            <h2 className="text-base font-semibold tracking-tight">{t('helpers.ui.timeline')}</h2>
            <StepTimeline
              order={orderOf(graph)}
              steps={stepOf}
              graph={graph}
              titles={titles}
              avatars={avatars}
              moods={shown}
              handoffs={run.handoffs}
              errText={errText}
              canResume={run.status === 'failed'}
              resuming={resume.isPending}
              onResume={() => resume.mutate(run.id)}
            />
          </section>

          <section className="space-y-3">
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
            {mapOpen &&
              (view === 'steps' ? (
                <StepsList
                  graph={graph}
                  specs={specs}
                  titles={titles}
                  avatars={avatars}
                  moods={shown}
                  selection={selection}
                  readOnly
                  onSelect={setSelection}
                />
              ) : (
                <Suspense fallback={<ListSkeleton rows={4} />}>
                  <Canvas
                    graph={graph}
                    specs={specs}
                    titles={titles}
                    avatars={avatars}
                    moods={shown}
                    packets={replayPackets ?? packets}
                    statusLabels={statusLabels}
                    selection={selection}
                    readOnly
                    onSelect={setSelection}
                  />
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
