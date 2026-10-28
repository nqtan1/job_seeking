import { CircleAlert, Loader2 } from 'lucide-react'
import { useI18n, type Key, type Vars } from '@/i18n'
import type { Citation } from './api'
import { noticeText, stepLabel, type Context, type Step } from './activity'

function contextLines(c: Context, t: (key: Key, vars?: Vars) => string, locale: string): string[] {
  const n = (v: number | undefined) => (v ?? 0).toLocaleString(locale)
  const cut = (x: { truncated?: boolean }) => (x.truncated ? ` ${t('coach.ctx.shortened')}` : '')
  const lines: string[] = []
  if (c.job) {
    lines.push(
      (c.job.title
        ? t('coach.ctx.job_titled', { title: c.job.title, chars: n(c.job.chars) })
        : t('coach.ctx.job', { chars: n(c.job.chars) })) + cut(c.job),
    )
  }
  if (c.profile) lines.push(t('coach.ctx.profile', { chars: n(c.profile.chars) }) + cut(c.profile))
  if (c.fit) lines.push(t('coach.ctx.fit', { chars: n(c.fit.chars) }))
  if (c.saved_jobs != null) lines.push(t('coach.ctx.saved_jobs', { n: c.saved_jobs }))
  if (c.history && (c.history.kept || c.history.dropped))
    lines.push(
      t('coach.ctx.history', { count: c.history.kept ?? 0 }) +
        (c.history.dropped ? `, ${t('coach.ctx.dropped', { n: c.history.dropped })}` : ''),
    )
  return lines
}

/** What the coach did for this reply, collapsed like a "worked for…" row: the steps it took,
 *  the web queries and sources, and exactly what was in its context. */
export function Activity({
  steps,
  context,
  queries = [],
  citations = [],
  notices = [],
  running = false,
}: {
  steps: Step[]
  context?: Context | null
  queries?: string[]
  citations?: Citation[]
  notices?: string[]
  running?: boolean
}) {
  const { t, locale } = useI18n()
  const lines = context ? contextLines(context, t, locale) : []
  if (!running && steps.length === 0 && lines.length === 0 && notices.length === 0) return null
  const summary = running
    ? steps.length
      ? t('coach.activity.working_steps', { count: steps.length })
      : t('coach.activity.working')
    : [
        steps.length
          ? t('coach.activity.steps', { count: steps.length })
          : t('coach.activity.context_used'),
        citations.length ? t('coach.activity.sources', { count: citations.length }) : '',
      ]
        .filter(Boolean)
        .join(' · ')
  return (
    <div className="space-y-1">
      <details
        open={running}
        className="rounded-lg border bg-card text-sm"
        aria-label={t('coach.activity.aria')}
      >
        <summary className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-muted-foreground select-none">
          {running && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
          <span role={running ? 'status' : undefined}>{summary}</span>
        </summary>
        <div className="space-y-2 border-t px-3 py-2">
          {steps.length > 0 && (
            <ol className="space-y-1">
              {steps.map((s) => (
                <li key={s.id} className="flex items-center gap-2">
                  {s.status === 'running' ? (
                    <Loader2 className="size-3.5 animate-spin" aria-hidden />
                  ) : s.status === 'error' ? (
                    <CircleAlert className="size-3.5 text-destructive" aria-hidden />
                  ) : (
                    <span className="size-3.5 text-center text-xs text-primary" aria-hidden>
                      ✓
                    </span>
                  )}
                  <span>{stepLabel(s, t)}</span>
                  {s.status === 'error' && (
                    <span className="text-destructive">{t('coach.activity.failed')}</span>
                  )}
                </li>
              ))}
            </ol>
          )}
          {queries.length > 0 && (
            <p className="text-muted-foreground">
              {t('coach.activity.searched', { queries: queries.join(' · ') })}
            </p>
          )}
          {lines.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">
                {t('coach.activity.in_context')}
              </p>
              <ul className="list-disc pl-5 text-muted-foreground">
                {lines.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </details>
      {notices.map((code) => (
        <p key={code} role="note" className="text-xs text-amber-600 dark:text-amber-400">
          {noticeText(code, t)}
        </p>
      ))}
    </div>
  )
}

/** Web sources, and Google's Search Suggestion chip: shown unmodified, in a sandboxed frame
 *  (it is third-party HTML: no scripts, no access to this page). */
export function Sources({
  citations,
  suggestionsHtml,
}: {
  citations: Citation[]
  suggestionsHtml?: string | null
}) {
  const { t } = useI18n()
  if (citations.length === 0 && !suggestionsHtml) return null
  return (
    <div className="mt-2 space-y-2 text-xs">
      {citations.length > 0 && (
        <div>
          <p className="font-medium text-muted-foreground">{t('coach.activity.sources_title')}</p>
          <ul className="space-y-0.5">
            {citations
              .filter((c) => /^https?:\/\//i.test(c.uri))
              .map((c) => (
                <li key={c.uri}>
                  <a
                    href={c.uri}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline underline-offset-2"
                  >
                    {c.title}
                  </a>
                </li>
              ))}
          </ul>
        </div>
      )}
      {suggestionsHtml && (
        <iframe
          title={t('coach.activity.suggestions_title')}
          srcDoc={suggestionsHtml}
          sandbox="allow-popups allow-popups-to-escape-sandbox"
          className="h-14 w-full rounded border-0"
        />
      )}
    </div>
  )
}
