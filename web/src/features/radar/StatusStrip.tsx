import { Radar } from 'lucide-react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { cn } from 'cn'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { useRadarStatus, useRunSearch } from './api'
import { stopText, when } from './format'

/** The radar at a glance: working or idle, what it did last, when it runs next. */
export function StatusStrip() {
  const { t, locale } = useI18n()
  const status = useRadarStatus(true)
  const retry = useRunSearch()
  if (!status.data) return null
  const { running, last_run: last, next_run_at: next, new_matches: matches, searches } = status.data
  const interrupted = status.data.interrupted && !running && last
  return (
    <div className="space-y-2">
      <section
        aria-label={t('radar.s.aria')}
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
            ? t('radar.s.working', { found: last?.found ?? 0, scored: last?.scored ?? 0 })
            : searches === 0
              ? t('radar.s.none')
              : t('radar.s.idle')}
        </p>
        {last && !running && (
          <p className="text-sm text-muted-foreground">
            {t('radar.s.last_run', {
              when: when(last.started_at, t, locale),
              count: last.scored,
              kept: last.shortlisted,
              stop:
                last.stop_reason && last.stop_reason !== 'done'
                  ? ` (${stopText(t, last.stop_reason)})`
                  : '',
            })}
          </p>
        )}
        <p className="text-sm text-muted-foreground">
          {next
            ? t('radar.s.next', { when: when(next, t, locale) })
            : searches
              ? t('radar.s.daily_off')
              : ''}
        </p>
        <p className="ml-auto flex items-center gap-1.5 text-sm font-medium">
          <Radar className="size-4 text-primary" />
          {t('radar.s.matches', { count: matches })}
        </p>
      </section>
      {interrupted && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm"
        >
          <p>
            <strong>{t('radar.s.interrupted')}</strong>
            {t('radar.s.interrupted_body', {
              reason: stopText(t, status.data.interrupted_reason ?? ''),
              count: last.found,
              scored: last.scored,
            })}
          </p>
          <Button size="sm" disabled={retry.isPending} onClick={() => retry.mutate(last.search_id)}>
            {t('radar.s.retry')}
          </Button>
          {retry.isError && <ErrorMessage error={retry.error} />}
        </div>
      )}
    </div>
  )
}
