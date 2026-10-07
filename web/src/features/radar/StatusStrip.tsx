import { Radar } from 'lucide-react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { cn } from 'cn'
import { Button } from '@/components/ui/button'
import { useRadarStatus, useRunSearch } from './api'
import { STOP, when } from './format'

/** The radar at a glance: working or idle, what it did last, when it runs next. */
export function StatusStrip() {
  const status = useRadarStatus(true)
  const retry = useRunSearch()
  if (!status.data) return null
  const { running, last_run: last, next_run_at: next, new_matches: matches, searches } = status.data
  const interrupted = status.data.interrupted && !running && last
  return (
    <div className="space-y-2">
      <section
        aria-label="Radar status"
        className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border bg-card p-4"
      >
        <p className="flex items-center gap-2 text-sm font-medium">
          <span
            className={cn(
              'size-2.5 rounded-full',
              running ? 'animate-pulse bg-success' : searches ? 'bg-muted-foreground' : 'bg-border',
            )}
          />
          {running
            ? `Working… found ${last?.found ?? 0}, scored ${last?.scored ?? 0}`
            : searches === 0
              ? 'No radar yet'
              : 'Idle'}
        </p>
        {last && !running && (
          <p className="text-sm text-muted-foreground">
            Last run {when(last.started_at)}: looked at {last.scored} new offer
            {last.scored === 1 ? '' : 's'}, kept {last.shortlisted}
            {last.stop_reason && last.stop_reason !== 'done' ? ` (${STOP[last.stop_reason]})` : ''}
          </p>
        )}
        <p className="text-sm text-muted-foreground">
          {next ? `Next run ${when(next)}` : searches ? 'Daily search is off' : ''}
        </p>
        <p className="ml-auto flex items-center gap-1.5 text-sm font-medium">
          <Radar className="size-4 text-primary" />
          {matches} new match{matches === 1 ? '' : 'es'}
        </p>
      </section>
      {interrupted && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm"
        >
          <p>
            <strong>The last run was interrupted</strong>
            {` (${STOP[status.data.interrupted_reason ?? ''] ?? 'something went wrong'}). It found ${last.found} offer${last.found === 1 ? '' : 's'} and scored ${last.scored}. Nothing was lost: a retry picks up the same offers.`}
          </p>
          <Button size="sm" disabled={retry.isPending} onClick={() => retry.mutate(last.search_id)}>
            Retry now
          </Button>
          {retry.isError && <ErrorMessage error={retry.error} />}
        </div>
      )}
    </div>
  )
}
