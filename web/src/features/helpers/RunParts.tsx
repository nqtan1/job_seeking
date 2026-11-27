import {
  Ban,
  Check,
  Circle,
  Clock,
  ExternalLink,
  Minus,
  Play,
  RotateCcw,
  Sparkles,
  Timer,
  X,
} from 'lucide-react'
import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { useI18n, useT } from '@/i18n'
import { Spinner } from '@/components/Spinner'
import {
  type Handoff,
  type Run,
  type Step,
  isLive,
  useCancelRun,
  useFlowRuns,
  useRerun,
  useResumeRun,
} from './api'
import { relTime, when } from '@/lib/time'
import { seconds } from './lib'
import { Result, RunStatusBadge } from './ui'
import { Link } from 'react-router'
import { ErrorMessage } from '@/components/ErrorMessage'
import { cn } from 'cn'
import { Button } from '@/components/ui/button'
import { Avatar } from './Avatar'
import { useErrText } from './playback'
import type { AvatarSpec, Mood } from './avatar'
import { type Graph, orderOf } from './graph'

function Stat({
  icon: Icon,
  children,
  title,
}: {
  icon: typeof Clock
  children: ReactNode
  title?: string
}) {
  return (
    <span title={title} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
      <Icon className="size-4 shrink-0" aria-hidden />
      {children}
    </span>
  )
}

function durationMs(run: Run): number | null {
  if (run.started_at && run.finished_at)
    return new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
  const sum = run.steps.reduce((n, s) => n + (s.latency_ms ?? 0), 0)
  return sum > 0 ? sum : null
}

/** What happened, at a glance: status, when, how long, how far, and what it cost. */
export function RunSummary({
  run,
  live,
  actions,
}: {
  run: Run
  live: boolean
  actions: ReactNode
}) {
  const { t, locale } = useI18n()
  const took = durationMs(run)
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div className="flex items-center gap-2">
        <RunStatusBadge status={run.status} />
        {live && <Spinner />}
      </div>
      <Stat icon={Clock} title={new Date(run.created_at).toLocaleString(locale)}>
        {relTime(run.created_at, locale)}
      </Stat>
      {took !== null && (
        <Stat icon={Timer}>{t('helpers.ui.took', { time: seconds(Math.max(took, 0)) })}</Stat>
      )}
      <span className="flex-1" />
      <div className="flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  )
}

/** The answer the person came for: a card with a header band, its fields as tiles and blocks. */
function ResultHero({ run }: { run: Run }) {
  const { t } = useI18n()
  if (run.status !== 'done') return null
  const has = Object.keys(run.result ?? {}).length > 0
  if (!has)
    return (
      <p role="status" className="rounded-xl bg-muted px-4 py-3 text-sm">
        {t('helpers.run.no_result')}
      </p>
    )
  const took = durationMs(run)
  const done = run.steps.filter((s) => s.status === 'done').length
  return (
    <section aria-label={t('helpers.node.output')} className="min-w-0">
      <Result
        value={run.result}
        large
        title={
          <div className="flex items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm">
              <Sparkles className="size-4.5" aria-hidden />
            </span>
            <div className="min-w-0">
              <h2 className="text-lg font-semibold tracking-tight">{t('helpers.node.output')}</h2>
              <p className="text-xs text-muted-foreground">
                {t('helpers.ui.steps_done', { count: done })}
                {took !== null &&
                  ` · ${t('helpers.ui.took', { time: seconds(Math.max(took, 0)) })}`}
              </p>
            </div>
          </div>
        }
      />
    </section>
  )
}

type Status = Step['status']

const RAIL: Record<Status, { icon: ReactNode; ring: string }> = {
  done: { icon: <Check className="size-3.5" />, ring: 'bg-success/15 text-success' },
  running: { icon: <Spinner />, ring: 'bg-accent text-accent-foreground' },
  failed: { icon: <X className="size-3.5" />, ring: 'bg-destructive/15 text-destructive' },
  skipped: { icon: <Minus className="size-3.5" />, ring: 'bg-muted text-muted-foreground' },
  waiting: { icon: <Clock className="size-3.5" />, ring: 'bg-muted text-muted-foreground' },
  pending: { icon: <Circle className="size-2" />, ring: 'bg-muted text-muted-foreground' },
}

type TraceProps = {
  run: Run
  order: string[]
  steps: Map<string, Step>
  graph: Graph
  titles: ReadonlyMap<string, string>
  avatars: ReadonlyMap<string, AvatarSpec>
  moods: ReadonlyMap<string, Mood>
  handoffs: Handoff[]
  errText: (code: string | null | undefined) => string
  canResume: boolean
  resuming: boolean
  onResume: () => void
}

/** Where each step sat in time, as fractions of the whole run (the waterfall bars). */
function useBars(steps: Step[]): Map<string, { left: number; width: number }> {
  return useMemo(() => {
    const t = (v: string | null) => (v ? new Date(v).getTime() : null)
    const starts = steps.map((s) => t(s.started_at)).filter((v): v is number => v !== null)
    const ends = steps.map((s) => t(s.finished_at)).filter((v): v is number => v !== null)
    if (starts.length === 0 || ends.length === 0) return new Map()
    const from = Math.min(...starts)
    const span = Math.max(Math.max(...ends) - from, 1)
    return new Map(
      steps.flatMap((s) => {
        const start = t(s.started_at)
        const end = t(s.finished_at) ?? from + span // still running: to the run's last known end
        if (start === null) return []
        const left = (start - from) / span
        return [
          [s.node_id, { left, width: Math.max(Math.min((end - start) / span, 1 - left), 0.02) }],
        ]
      }),
    )
  }, [steps])
}

/** What to open first: the failed step, else the result of a finished run, else the last real step. */
function firstPick(rows: string[], steps: Map<string, Step>, graph: Graph, run: Run) {
  const typeOf = (id: string) => graph.nodes.find((n) => n.id === id)?.type
  const work = (id: string) => typeOf(id) !== 'input' && typeOf(id) !== 'output'
  return (
    rows.find((id) => steps.get(id)?.status === 'failed') ??
    (run.status === 'done' ? rows.find((id) => typeOf(id) === 'output') : undefined) ??
    [...rows].reverse().find((id) => work(id) && steps.get(id)?.status === 'done') ??
    rows.at(-1)
  )
}

/**
 * The run as a trace: the flow top to bottom on the left (status, name, time, a waterfall bar per
 * step, joined by a line) and, beside it with the room it needs, the selected step's input and
 * output, or the result card. Stacked on a narrow screen or panel.
 */
export function Trace(p: TraceProps) {
  const t = useT()
  const rows = p.order.filter((id) => p.steps.has(id))
  const bars = useBars([...p.steps.values()])
  const [chosen, setChosen] = useState<string | null>(null)
  const selected = chosen && p.steps.has(chosen) ? chosen : firstPick(rows, p.steps, p.graph, p.run)
  const step = selected ? p.steps.get(selected) : undefined
  const node = p.graph.nodes.find((n) => n.id === selected)
  // a finished run opens on its answer, even before its Result step is listed
  return (
    <div className="@container">
      <div className="grid items-start gap-5 @3xl:grid-cols-[minmax(15rem,19rem)_minmax(0,1fr)]">
        <ol
          aria-label={t('helpers.view.steps')}
          className="rounded-2xl border bg-muted/30 p-2 @3xl:sticky @3xl:top-4"
        >
          {rows.map((id, i) => (
            <TraceRow
              key={id}
              step={p.steps.get(id)!}
              title={p.titles.get(id) ?? ''}
              avatar={p.avatars.get(id)}
              mood={p.moods.get(id)}
              bar={bars.get(id)}
              last={i === rows.length - 1}
              selected={id === selected}
              onSelect={() => setChosen(id)}
            />
          ))}
        </ol>
        {p.run.status === 'done' && (chosen === null || node?.type === 'output') ? (
          <ResultHero run={p.run} />
        ) : (
          selected &&
          step && (
            <StepPanel
              key={selected}
              step={step}
              node={node}
              title={p.titles.get(selected) ?? ''}
              received={p.handoffs.filter((h) => h.to_node === selected)}
              errText={p.errText}
              canResume={p.canResume}
              resuming={p.resuming}
              onResume={p.onResume}
            />
          )
        )}
      </div>
    </div>
  )
}

function TraceRow({
  step: s,
  title,
  avatar,
  mood,
  bar,
  last,
  selected,
  onSelect,
}: {
  step: Step
  title: string
  avatar: AvatarSpec | undefined
  mood: Mood | undefined
  bar: { left: number; width: number } | undefined
  last: boolean
  selected: boolean
  onSelect: () => void
}) {
  const t = useT()
  const rail = RAIL[s.status]
  return (
    <li className="relative">
      {!last && (
        <span aria-hidden className="absolute top-9 -bottom-1 left-[1.4rem] w-px bg-border" />
      )}
      <button
        type="button"
        aria-pressed={selected}
        onClick={onSelect}
        className={cn(
          'relative flex w-full gap-3 rounded-xl px-2.5 py-2.5 text-left text-sm outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50',
          selected ? 'bg-background shadow-sm ring-1 ring-primary/30' : 'hover:bg-background/70',
        )}
      >
        <span
          className={cn(
            'grid size-6 shrink-0 place-items-center rounded-full ring-4 ring-muted/30',
            rail.ring,
          )}
        >
          {rail.icon}
          <span className="sr-only">{t(`helpers.run.status.${s.status}`)}</span>
        </span>
        <span className="min-w-0 flex-1 space-y-1.5">
          <span className="flex items-center gap-2">
            {avatar && <Avatar spec={avatar} mood={mood} size={20} />}
            <span className="min-w-0 flex-1 truncate font-medium">{title}</span>
            {s.latency_ms != null && (
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                {seconds(s.latency_ms)}
              </span>
            )}
          </span>
          {bar && (
            <span aria-hidden className="relative block h-1 rounded-full bg-muted">
              <span
                className={cn(
                  'absolute inset-y-0 rounded-full',
                  s.status === 'failed' ? 'bg-destructive/70' : 'bg-primary/60',
                )}
                style={{ left: `${bar.left * 100}%`, width: `${bar.width * 100}%` }}
              />
            </span>
          )}
        </span>
      </button>
    </li>
  )
}

function StepFailure({
  node,
  message,
  canResume,
  resuming,
  onResume,
}: {
  node: Graph['nodes'][number] | undefined
  message: string
  canResume: boolean
  resuming: boolean
  onResume: () => void
}) {
  const t = useT()
  return (
    <div
      role="alert"
      className="space-y-3 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm"
    >
      <p className="text-destructive">{message}</p>
      <div className="flex flex-wrap gap-2">
        {node?.type === 'agent' && (
          <Link
            to={`/helpers/${node.agent_id}`}
            className="inline-flex h-8 items-center rounded-lg border bg-background px-2.5 text-sm font-medium hover:bg-muted pointer-coarse:h-11"
          >
            {t('helpers.inspect.edit_helper')}
          </Link>
        )}
        {canResume && (
          <Button size="sm" disabled={resuming} onClick={onResume}>
            {resuming ? <Spinner /> : <RotateCcw data-icon="inline-start" />}
            {t('helpers.run.resume')}
          </Button>
        )}
      </div>
    </div>
  )
}

function StepPanel({
  step: s,
  node,
  title,
  received,
  errText,
  canResume,
  resuming,
  onResume,
}: {
  step: Step
  node: Graph['nodes'][number] | undefined
  title: string
  received: Handoff[]
  errText: (code: string | null | undefined) => string
  canResume: boolean
  resuming: boolean
  onResume: () => void
}) {
  const t = useT()
  const input = Object.assign({}, ...received.map((h) => h.payload)) as Record<string, unknown>
  return (
    <section aria-label={title} className="min-w-0 space-y-3">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="font-semibold">{title}</h3>
        <span className="text-xs text-muted-foreground">
          {t(`helpers.run.status.${s.status}`)}
          {s.latency_ms != null && ` · ${seconds(s.latency_ms)}`}
          {s.model && ` · ${s.model}`}
        </span>
      </header>
      {s.status === 'skipped' && (
        <p className="text-sm text-muted-foreground">{t('helpers.step.skipped_why')}</p>
      )}
      {s.status === 'failed' && (
        <StepFailure
          node={node}
          message={errText(s.error_code)}
          canResume={canResume}
          resuming={resuming}
          onResume={onResume}
        />
      )}
      {received.length > 0 && (
        <Result value={input} bare title={<PaneTitle>{t('helpers.ui.received')}</PaneTitle>} />
      )}
      {s.output ? (
        <Result value={s.output} title={<PaneTitle>{t('helpers.ui.produced')}</PaneTitle>} />
      ) : (
        <p className="rounded-xl bg-muted px-4 py-3 text-sm text-muted-foreground">
          {t('helpers.ui.nothing')}
        </p>
      )}
    </section>
  )
}

function PaneTitle({ children }: { children: ReactNode }) {
  return (
    <h4 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
      {children}
    </h4>
  )
}

/** The last runs of a flow, so a result can be found again after leaving its run page. */
export function RecentRuns({ flowId }: { flowId: string }) {
  const { t, locale } = useI18n()
  const runs = useFlowRuns(flowId).data
  if (!runs?.length) return null
  return (
    <section aria-label={t('helpers.pages.runs.list')} className="space-y-2 rounded-xl border p-4">
      <h2 className="font-semibold">{t('helpers.pages.runs.list')}</h2>
      <ul className="divide-y">
        {runs.slice(0, 5).map((r) => (
          <li key={r.id}>
            <Link
              to={`/automations/runs/${r.id}`}
              className="flex items-center justify-between gap-3 rounded py-2 text-sm outline-none hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <RunStatusBadge status={r.status} />
              <span className="text-muted-foreground">{relTime(r.created_at, locale)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Milliseconds since `since`, refreshed every second while `live`; stops at `until` when given. */
function useElapsed(since: string, until: string | null | undefined, live: boolean): number {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    if (!live) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [live])
  const end = live || !until ? now : new Date(until).getTime()
  return Math.max(Math.floor((end - new Date(since).getTime()) / 1000) * 1000, 0)
}

function LiveHeader({ run, live, elapsed }: { run: Run; live: boolean; elapsed: number }) {
  const { t, locale } = useI18n()
  return (
    <>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 className="font-semibold tracking-tight">{t('helpers.live.title')}</h2>
        <RunStatusBadge status={run.status} />
        {live && <Spinner />}
        <span className="text-sm text-muted-foreground tabular-nums">
          {t(live ? 'helpers.live.elapsed' : 'helpers.ui.took', { time: seconds(elapsed) })}
        </span>
      </div>
      <div role="status" className="sr-only">
        {t(`helpers.run.status.${run.status}`)}
      </div>
      {run.status === 'waiting' && (
        <p className="text-sm text-muted-foreground">
          {t('helpers.run.waiting_until', { time: when(run.wake_at, locale) })}
        </p>
      )}
    </>
  )
}

function LiveActions({
  run,
  live,
  stepFailed,
  cancel,
  rerun,
  resume,
  onFollow,
  onClose,
}: {
  run: Run
  live: boolean
  stepFailed: boolean
  cancel: ReturnType<typeof useCancelRun>
  rerun: ReturnType<typeof useRerun>
  resume: ReturnType<typeof useResumeRun>
  onFollow: (runId: string) => void
  onClose: () => void
}) {
  const t = useT()
  return (
    <div className="flex flex-wrap gap-2">
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
      {!live && (
        <Button
          size="sm"
          variant={run.status === 'done' ? 'default' : 'outline'}
          disabled={rerun.isPending}
          onClick={() => rerun.mutate(run.id, { onSuccess: (r) => onFollow(r.id) })}
        >
          {rerun.isPending ? <Spinner /> : <Play data-icon="inline-start" />}
          {t('helpers.live.again')}
        </Button>
      )}
      <Link
        to={`/automations/runs/${run.id}`}
        className="inline-flex h-7 items-center gap-1 rounded-lg border bg-background px-2.5 text-sm font-medium hover:bg-muted pointer-coarse:h-11"
      >
        <ExternalLink className="size-3.5" aria-hidden />
        {t('helpers.live.full')}
      </Link>
      <Button variant="ghost" size="sm" onClick={onClose}>
        <X data-icon="inline-start" />
        {t('helpers.live.close')}
      </Button>
    </div>
  )
}

/**
 * A run followed in place (the flow editor): status and timer, the steps as they start, the
 * answer with Copy, and what to do next. The status line is always mounted so changes are spoken.
 */
export function LiveRunPanel({
  run,
  graph,
  titles,
  avatars,
  moods,
  onFollow,
  onClose,
}: {
  run: Run
  graph: Graph
  titles: ReadonlyMap<string, string>
  avatars: ReadonlyMap<string, AvatarSpec>
  moods: ReadonlyMap<string, Mood>
  onFollow: (runId: string) => void
  onClose: () => void
}) {
  const { t } = useI18n()
  const errText = useErrText()
  const live = isLive(run.status)
  const cancel = useCancelRun()
  const rerun = useRerun()
  const resume = useResumeRun()
  const elapsed = useElapsed(run.started_at ?? run.created_at, run.finished_at, live)
  const started = new Map(
    run.steps.filter((s) => s.status !== 'pending').map((s) => [s.node_id, s]),
  )
  const stepFailed = run.steps.some((s) => s.status === 'failed')
  return (
    <section
      aria-label={t('helpers.live.title')}
      className="space-y-4 rounded-2xl border bg-card p-4 shadow-xs"
    >
      <LiveHeader run={run} live={live} elapsed={elapsed} />
      <LiveActions
        run={run}
        live={live}
        stepFailed={stepFailed}
        cancel={cancel}
        rerun={rerun}
        resume={resume}
        onFollow={onFollow}
        onClose={onClose}
      />
      <ErrorMessage error={cancel.error ?? rerun.error ?? resume.error} />
      {run.status === 'failed' && (
        <p className="text-sm text-muted-foreground">
          {run.error_code && !stepFailed ? errText(run.error_code) : t('helpers.rerr.generic')}
        </p>
      )}
      {run.status === 'cancelled' && (
        <p className="text-sm text-muted-foreground">{t('helpers.rerr.cancelled')}</p>
      )}
      {started.size === 0 && live && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner />
          {t('helpers.run.status.queued')}
        </p>
      )}
      <Trace
        run={run}
        order={orderOf(graph)}
        steps={started}
        graph={graph}
        titles={titles}
        avatars={avatars}
        moods={moods}
        handoffs={run.handoffs}
        errText={errText}
        canResume={run.status === 'failed'}
        resuming={resume.isPending}
        onResume={() => resume.mutate(run.id)}
      />
    </section>
  )
}
