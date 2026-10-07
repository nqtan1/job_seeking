import { Radar } from 'lucide-react'
import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { ListSkeleton } from '@/components/Skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { Button, buttonVariants } from '@/components/ui/button'
import { ApplyActions } from '@/features/pipeline/ApplyActions'
import { useDecide, useKeepAnyway, useMarkSeen, useResults, type Result } from './api'
import { foundOn } from './format'

const tone = (score: number) => (score >= 80 ? 'success' : score >= 65 ? 'warning' : 'neutral')

/** Why it matched, in the user's words: two strengths and the main thing to watch. */
function Why({ r }: { r: Result }) {
  const { strengths, gaps, missing } = r.highlights
  const watch = missing[0] ?? gaps[0]
  if (strengths.length === 0 && !watch) return null
  return (
    <div className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
      {strengths.length > 0 && (
        <div>
          <p className="text-xs font-medium text-success">Why it fits</p>
          <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
            {strengths.slice(0, 2).map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      )}
      {watch && (
        <div>
          <p className="text-xs font-medium text-warning">To watch</p>
          <p className="text-muted-foreground">{watch}</p>
        </div>
      )}
    </div>
  )
}

export function NewMatches() {
  const results = useResults('new')
  const decide = useDecide()
  const navigate = useNavigate()
  const { mutate: markSeen } = useMarkSeen()
  const shown = results.data?.length ?? 0
  useEffect(() => {
    if (shown > 0) markSeen()
  }, [shown, markSeen])
  if (results.isPending) return <ListSkeleton rows={2} />
  if (results.isError) return <ErrorMessage error={results.error} />
  if (results.data.length === 0)
    return (
      <EmptyState
        icon={Radar}
        title="No new matches"
        description="They appear here after a run, with the reasons. You decide what happens next: nothing is sent anywhere."
      />
    )
  return (
    <ul className="space-y-3">
      {results.data.map((r) => (
        <li key={r.id} className="space-y-3 rounded-xl border bg-card p-4 shadow-xs">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate font-medium">{r.title ?? 'Job'}</p>
              <p className="truncate text-sm text-muted-foreground">
                {r.company} · {foundOn(r.found_at)}
                {r.search_name ? ` · from “${r.search_name}”` : ''}
              </p>
            </div>
            <StatusBadge tone={tone(r.score ?? 0)}>Fit {Math.round(r.score ?? 0)}%</StatusBadge>
          </div>
          <Why r={r} />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              disabled={decide.isPending}
              onClick={() =>
                decide.mutate(
                  { id: r.id, action: 'approve' },
                  { onSuccess: () => r.job_id && navigate(`/letters?job=${r.job_id}`) },
                )
              }
            >
              Keep and write a letter
            </Button>
            {r.job_id && (
              <Link
                to={`/jobs/${r.job_id}/fit`}
                className={buttonVariants({ variant: 'outline', size: 'sm' })}
              >
                Job &amp; analysis
              </Link>
            )}
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Dismiss ${r.title ?? 'job'}`}
              disabled={decide.isPending}
              onClick={() => decide.mutate({ id: r.id, action: 'dismiss' })}
            >
              Not interested
            </Button>
          </div>
        </li>
      ))}
      {decide.isError && <ErrorMessage error={decide.error} />}
    </ul>
  )
}

/** Matches the user kept: follow each one through to the tracker. */
export function InProgress() {
  const results = useResults('approved')
  if (!results.data || results.data.length === 0) return null
  return (
    <section aria-label="Following up" className="space-y-2">
      <h2 className="text-sm font-semibold text-muted-foreground">Following up</h2>
      <ul className="space-y-2">
        {results.data.map((r) => (
          <li
            key={r.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card p-3"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{r.title ?? 'Job'}</p>
              <p className="truncate text-xs text-muted-foreground">
                {r.company} · Fit {Math.round(r.score ?? 0)}%
              </p>
            </div>
            {r.job_id && (
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  to={`/jobs/${r.job_id}/fit`}
                  className={buttonVariants({ variant: 'outline', size: 'sm' })}
                >
                  Job &amp; analysis
                </Link>
                <ApplyActions jobId={r.job_id} jobSource="france_travail" />
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

/** What the radar looked at and did not shortlist, so nothing is hidden from the user. */
export function Rejected({ minScore }: { minScore: number | undefined }) {
  const results = useResults('skipped')
  const keep = useKeepAnyway()
  const navigate = useNavigate()
  if (!results.data || results.data.length === 0) return null
  return (
    <details className="rounded-xl border bg-card p-4">
      <summary className="cursor-pointer text-sm font-medium">
        Checked but not shortlisted ({results.data.length})
      </summary>
      <p className="mt-2 text-xs text-muted-foreground">
        These scored below your minimum{minScore ? ` of ${minScore}%` : ''}. If you disagree, review
        one anyway.
      </p>
      <ul className="mt-2 space-y-2">
        {results.data.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <div className="min-w-0">
              <p className="truncate">
                {r.title ?? 'Job'} <span className="text-muted-foreground">· {r.company}</span>
              </p>
              <p className="truncate text-xs text-muted-foreground">
                Fit {Math.round(r.score ?? 0)}%
                {r.highlights.missing[0] ? ` · missing: ${r.highlights.missing[0]}` : ''}
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              aria-label={`Review ${r.title ?? 'job'} anyway`}
              disabled={keep.isPending}
              onClick={() =>
                keep.mutate(r.id, { onSuccess: (k) => navigate(`/jobs/${k.job_id}/fit`) })
              }
            >
              Review anyway
            </Button>
          </li>
        ))}
      </ul>
      {keep.isError && <ErrorMessage error={keep.error} />}
    </details>
  )
}
