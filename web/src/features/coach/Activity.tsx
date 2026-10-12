import { CircleAlert, Loader2 } from 'lucide-react'
import type { Citation } from './api'
import { NOTICES, type Context, type Step } from './activity'

const n = (v: number | undefined) => (v ?? 0).toLocaleString()

function contextLines(c: Context): string[] {
  const lines: string[] = []
  if (c.job) {
    lines.push(
      `Job${c.job.title ? `: ${c.job.title}` : ''} · ${n(c.job.chars)} characters${c.job.truncated ? ' (shortened)' : ''}`,
    )
  }
  if (c.profile)
    lines.push(
      `Your profile · ${n(c.profile.chars)} characters${c.profile.truncated ? ' (shortened)' : ''}`,
    )
  if (c.fit) lines.push(`Fit analysis · ${n(c.fit.chars)} characters`)
  if (c.saved_jobs != null) lines.push(`Saved jobs · ${c.saved_jobs} listed`)
  if (c.history && (c.history.kept || c.history.dropped))
    lines.push(
      `Conversation · ${c.history.kept ?? 0} earlier message${c.history.kept === 1 ? '' : 's'}` +
        (c.history.dropped ? `, ${c.history.dropped} too old to include` : ''),
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
  const lines = context ? contextLines(context) : []
  if (!running && steps.length === 0 && lines.length === 0 && notices.length === 0) return null
  const summary = running
    ? steps.length
      ? `Working… ${steps.length} step${steps.length > 1 ? 's' : ''}`
      : 'Working…'
    : [
        steps.length ? `${steps.length} step${steps.length > 1 ? 's' : ''}` : 'Context used',
        citations.length ? `${citations.length} source${citations.length > 1 ? 's' : ''}` : '',
      ]
        .filter(Boolean)
        .join(' · ')
  return (
    <div className="space-y-1">
      <details open={running} className="rounded-lg border bg-card text-sm" aria-label="Activity">
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
                  <span>{s.label}</span>
                  {s.status === 'error' && <span className="text-destructive">(failed)</span>}
                </li>
              ))}
            </ol>
          )}
          {queries.length > 0 && (
            <p className="text-muted-foreground">Searched for: {queries.join(' · ')}</p>
          )}
          {lines.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">In its context</p>
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
          {NOTICES[code] ?? code}
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
  if (citations.length === 0 && !suggestionsHtml) return null
  return (
    <div className="mt-2 space-y-2 text-xs">
      {citations.length > 0 && (
        <div>
          <p className="font-medium text-muted-foreground">Sources</p>
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
          title="Google Search suggestions"
          srcDoc={suggestionsHtml}
          sandbox="allow-popups allow-popups-to-escape-sandbox"
          className="h-14 w-full rounded border-0"
        />
      )}
    </div>
  )
}
