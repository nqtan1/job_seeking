import { Play } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { type Key, catalogs, useI18n } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { ListSkeleton } from '@/components/Skeleton'
import { Spinner } from '@/components/Spinner'
import { Button, buttonVariants } from '@/components/ui/button'
import { NativeSelect } from '@/components/ui/native-select'
import { Label } from '@/components/ui/label'
import { cn } from 'cn'
import { type RunListItem, type RunSummary, isLive, useAllRuns, useFlows, useRerun } from './api'
import { relTime, when } from './lib'
import { RunStatusBadge } from './ui'

const FILTERS = ['all', 'running', 'waiting', 'done', 'failed'] as const
type Filter = (typeof FILTERS)[number]

/** One plain sentence on what happened, for people who never saw an error code. */
function useOutcome() {
  const { t, locale } = useI18n()
  return (r: RunListItem) => {
    if (r.status === 'queued') return t('helpers.pages.runs.waiting')
    if (r.status === 'waiting')
      return t('helpers.run.waiting_until', { time: when(r.wake_at, locale) })
    if (r.status === 'running') return t('helpers.pages.runs.working')
    if (r.status === 'done') return t('helpers.pages.runs.done')
    const key = `helpers.rerr.${r.status === 'cancelled' ? 'cancelled' : r.error_code}`
    return t((key in catalogs.en ? key : 'helpers.rerr.generic') as Key)
  }
}

const TRIGGER = {
  schedule: 'helpers.pages.runs.by_schedule',
  flow: 'helpers.pages.runs.by_flow',
} as const satisfies Record<string, Key>

function RunRow({ run }: { run: RunListItem }) {
  const { t, locale } = useI18n()
  const navigate = useNavigate()
  const again = useRerun()
  const outcome = useOutcome()
  return (
    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/automations/runs/${run.id}`}
            aria-label={t('helpers.pages.runs.open', { name: run.flow_name })}
            className="truncate rounded font-semibold outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {run.flow_name}
          </Link>
          <RunStatusBadge status={run.status} />
        </div>
        {run.status !== 'done' && (
          <p
            className={cn(
              'flex items-center gap-2 text-sm',
              run.status === 'failed' ? 'text-destructive' : 'text-muted-foreground',
            )}
          >
            {isLive(run.status) && <Spinner />}
            {outcome(run)}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          <time dateTime={run.created_at} title={new Date(run.created_at).toLocaleString(locale)}>
            {relTime(run.created_at, locale)}
          </time>
          {run.trigger !== 'manual' && (
            <>
              {' · '}
              <span>{t(TRIGGER[run.trigger])}</span>
            </>
          )}
        </p>
        <ErrorMessage error={again.error} />
      </div>
      <Button
        variant="ghost"
        size="sm"
        disabled={again.isPending || isLive(run.status)}
        aria-label={t('helpers.pages.runs.again_label', { name: run.flow_name })}
        onClick={() =>
          again.mutate(run.id, { onSuccess: (r) => navigate(`/automations/runs/${r.id}`) })
        }
      >
        {again.isPending ? <Spinner /> : <Play data-icon="inline-start" />}
        {t('helpers.pages.runs.again')}
      </Button>
    </li>
  )
}

/** The "Runs" tab: everything that ran, newest first, with simple filters. */
export function RunsTab() {
  const { t } = useI18n()
  const [filter, setFilter] = useState<Filter>('all')
  const [flowId, setFlowId] = useState('')
  const flows = useFlows()
  const runs = useAllRuns({
    status: filter === 'all' ? undefined : (filter as RunSummary['status']),
    flowId: flowId || undefined,
  })
  const rows = runs.data?.pages.flat() ?? []
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div
          role="group"
          aria-label={t('helpers.pages.runs.list')}
          className="flex flex-wrap gap-2"
        >
          {FILTERS.map((f) => (
            <Button
              key={f}
              size="sm"
              variant={filter === f ? 'outline' : 'ghost'}
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
            >
              {f === 'all' ? t('helpers.pages.runs.all') : t(`helpers.run.status.${f}`)}
            </Button>
          ))}
        </div>
        <div className="ml-auto space-y-1">
          <Label htmlFor="runs-flow" className="sr-only">
            {t('helpers.pages.runs.flow')}
          </Label>
          <NativeSelect id="runs-flow" value={flowId} onChange={(e) => setFlowId(e.target.value)}>
            <option value="">{t('helpers.pages.runs.flow_all')}</option>
            {(flows.data ?? []).map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>
      {runs.isPending ? (
        <ListSkeleton />
      ) : runs.error ? (
        <ErrorMessage error={runs.error} />
      ) : rows.length === 0 ? (
        <div className="flex flex-wrap items-center gap-3 py-6 text-sm text-muted-foreground">
          {t(
            filter === 'all' && !flowId
              ? 'helpers.pages.runs.empty'
              : 'helpers.pages.runs.empty_filtered',
          )}
          <Link to="/automations" className={buttonVariants({ variant: 'outline' })}>
            {t('helpers.pages.runs.go')}
          </Link>
        </div>
      ) : (
        <>
          <ul aria-label={t('helpers.pages.runs.list')} className="divide-y rounded-2xl border">
            {rows.map((r) => (
              <RunRow key={r.id} run={r} />
            ))}
          </ul>
          {runs.hasNextPage && (
            <div className="flex justify-center">
              <Button
                variant="outline"
                disabled={runs.isFetchingNextPage}
                onClick={() => runs.fetchNextPage()}
              >
                {runs.isFetchingNextPage && <Spinner />}
                {t('helpers.pages.runs.more')}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
