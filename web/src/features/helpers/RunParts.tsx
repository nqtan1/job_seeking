import {
  Ban,
  Bot,
  Check,
  ChevronDown,
  Circle,
  Clock,
  ExternalLink,
  ListChecks,
  Minus,
  Play,
  RotateCcw,
  Timer,
  X,
} from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'
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
import { relTime, seconds, when } from './lib'
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
  const done = run.steps.filter((s) => s.status === 'done' || s.status === 'skipped').length
  const uses = run.steps.filter((s) => s.model).length
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-2xl border bg-card p-4 shadow-xs">
      <div className="flex items-center gap-2">
        <RunStatusBadge status={run.status} />
        {live && <Spinner />}
      </div>
      <Stat icon={Clock} title={new Date(run.created_at).toLocaleString(locale)}>
        <span>
          {relTime(run.created_at, locale)}
          <span className="hidden text-muted-foreground/70 sm:inline">
            {' · '}
            {new Date(run.created_at).toLocaleString(locale)}
          </span>
        </span>
      </Stat>
      {took !== null && (
        <Stat icon={Timer}>{t('helpers.ui.took', { time: seconds(Math.max(took, 0)) })}</Stat>
      )}
      <Stat icon={ListChecks}>{t('helpers.ui.steps_of', { done, count: run.steps.length })}</Stat>
      <Stat icon={Bot}>{t('helpers.ui.ai_uses', { count: uses })}</Stat>
      <span className="flex-1" />
      <div className="flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  )
}

/** The answer the person came for, first and in reading size. */
export function ResultHero({ run }: { run: Run }) {
  const { t } = useI18n()
  if (run.status !== 'done') return null
  const has = Object.keys(run.result ?? {}).length > 0
  if (!has)
    return (
      <p role="status" className="rounded-xl bg-muted px-4 py-3 text-sm">
        {t('helpers.run.no_result')}
      </p>
    )
  return (
    <section
      aria-label={t('helpers.run.result')}
      className="space-y-2 rounded-2xl border-2 border-primary/30 bg-gradient-to-br from-primary/5 to-transparent p-5 shadow-sm"
    >
      <h2 className="text-lg font-semibold tracking-tight">{t('helpers.run.result')}</h2>
      <Result value={run.result} large />
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

/** The run, top to bottom: one row per step on a connecting line. Details stay folded until asked
 *  for, except on a failed step, where the reason and what to do about it are the point. */
export function StepTimeline({
  order,
  steps,
  graph,
  titles,
  avatars,
  moods,
  handoffs,
  errText,
  canResume,
  resuming,
  onResume,
}: {
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
}) {
  const t = useT()
  const rows = order.filter((id) => steps.has(id))
  return (
    <ol aria-label={t('helpers.timeline')} className="space-y-0">
      {rows.map((id, i) => (
        <Row
          key={id}
          last={i === rows.length - 1}
          step={steps.get(id)!}
          node={graph.nodes.find((n) => n.id === id)}
          title={titles.get(id) ?? ''}
          avatar={avatars.get(id)}
          mood={moods.get(id)}
          received={handoffs.filter((h) => h.to_node === id)}
          errText={errText}
          canResume={canResume}
          resuming={resuming}
          onResume={onResume}
        />
      ))}
    </ol>
  )
}

function Row({
  step: s,
  node,
  title,
  avatar,
  mood,
  received,
  last,
  errText,
  canResume,
  resuming,
  onResume,
}: {
  step: Step
  node: Graph['nodes'][number] | undefined
  title: string
  avatar: AvatarSpec | undefined
  mood: Mood | undefined
  received: Handoff[]
  last: boolean
  errText: (code: string | null | undefined) => string
  canResume: boolean
  resuming: boolean
  onResume: () => void
}) {
  const t = useT()
  const failed = s.status === 'failed'
  const [open, setOpen] = useState(failed)
  const quiet = node?.type === 'output' || node?.type === 'input'
  const hasDetails = !quiet && (s.output != null || received.length > 0)
  const rail = RAIL[s.status]
  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      {!last && <span aria-hidden className="absolute top-8 bottom-0 left-3.5 w-px bg-border" />}
      <span
        className={cn('relative grid size-7 shrink-0 place-items-center rounded-full', rail.ring)}
      >
        {rail.icon}
        <span className="sr-only">{t(`helpers.step.${s.status}`)}</span>
      </span>
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex min-h-7 flex-wrap items-center gap-2">
          {avatar && <Avatar spec={avatar} mood={mood} size={28} />}
          <span className={cn('font-medium', quiet && 'text-muted-foreground')}>{title}</span>
          {s.latency_ms != null && (
            <span className="text-xs text-muted-foreground tabular-nums">
              {seconds(s.latency_ms)}
            </span>
          )}
          <span className="flex-1" />
          {hasDetails && (
            <Button
              variant="ghost"
              size="xs"
              aria-expanded={open}
              onClick={() => setOpen((o) => !o)}
            >
              {t('helpers.ui.details')}
              <ChevronDown
                data-icon="inline-end"
                className={cn('transition-transform duration-200', open && 'rotate-180')}
              />
            </Button>
          )}
        </div>
        {s.status === 'skipped' && (
          <p className="text-sm text-muted-foreground">{t('helpers.step.skipped_why')}</p>
        )}
        {failed && (
          <div
            role="alert"
            className="space-y-3 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm"
          >
            <p className="text-destructive">{errText(s.error_code)}</p>
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
        )}
        {hasDetails && open && (
          <div className="space-y-3 rounded-xl border bg-muted/30 p-3">
            {received.length > 0 && (
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">
                  {t('helpers.ui.received')}
                </p>
                {received.map((h) => (
                  <Result key={h.edge_id} value={h.payload} bare />
                ))}
              </div>
            )}
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">
                {t('helpers.ui.produced')}
              </p>
              {s.output ? (
                <Result value={s.output} bare />
              ) : (
                <p className="text-sm text-muted-foreground">{t('helpers.ui.nothing')}</p>
              )}
            </div>
          </div>
        )}
      </div>
    </li>
  )
}

/** The last runs of a flow, so a result can be found again after leaving its run page. */
export function RecentRuns({ flowId }: { flowId: string }) {
  const { t, locale } = useI18n()
  const runs = useFlowRuns(flowId).data
  if (!runs?.length) return null
  return (
    <section aria-label={t('helpers.flow.recent')} className="space-y-2 rounded-xl border p-4">
      <h2 className="font-semibold">{t('helpers.flow.recent')}</h2>
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
  const { t, locale } = useI18n()
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
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 className="font-semibold tracking-tight">{t('helpers.live.title')}</h2>
        <RunStatusBadge status={run.status} />
        {live && <Spinner />}
        <span className="text-sm text-muted-foreground tabular-nums">
          {t(live ? 'helpers.live.elapsed' : 'helpers.live.total', { time: seconds(elapsed) })}
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
      <ErrorMessage error={cancel.error ?? rerun.error ?? resume.error} />
      {run.status === 'failed' && (
        <p className="text-sm text-muted-foreground">
          {run.error_code && !stepFailed ? errText(run.error_code) : t('helpers.live.failed')}
        </p>
      )}
      {run.status === 'cancelled' && (
        <p className="text-sm text-muted-foreground">{t('helpers.live.stopped')}</p>
      )}
      {started.size === 0 && live && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner />
          {t('helpers.live.starting')}
        </p>
      )}
      <StepTimeline
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
      <ResultHero run={run} />
    </section>
  )
}
