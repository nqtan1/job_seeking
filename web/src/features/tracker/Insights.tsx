import { Link } from 'react-router'
import { StatusBadge } from '@/components/StatusBadge'
import { Button, buttonVariants } from '@/components/ui/button'
import { useChangeStatus, useFunnel, type Application } from './api'
import { needsAttention } from './attention'
import { sourceLabel } from './constants'

/** What works: replies and interviews by source, from the user's own tracker. */
export function Funnel() {
  const rows = useFunnel().data?.rows ?? []
  if (rows.length === 0) return null
  return (
    <details className="group rounded-xl border p-4">
      <summary className="cursor-pointer rounded text-sm font-semibold outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
        What works, by source
      </summary>
      <ul aria-label="What works" className="mt-2 space-y-1 text-sm">
        {rows.map((r) => (
          <li key={r.source} className="flex flex-wrap justify-between gap-2">
            <span className="capitalize">{sourceLabel(r.source)}</span>
            <span className="text-muted-foreground">
              {r.sent} sent · {r.replied} replied · {r.interviews} interview
              {r.interviews === 1 ? '' : 's'}
            </span>
          </li>
        ))}
      </ul>
    </details>
  )
}

/** "Needs attention": a follow-up to send, or an interview coming up. */
export function AttentionPanel({ apps }: { apps: Application[] }) {
  const change = useChangeStatus()
  const items = needsAttention(apps)
  if (items.length === 0) return null
  return (
    <section
      aria-label="Needs attention"
      className="space-y-2 rounded-xl border border-warning/40 bg-warning/10 p-4"
    >
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        Needs attention <StatusBadge tone="warning">{items.length}</StatusBadge>
      </h2>
      <ul className="space-y-2 text-sm">
        {items.map(({ app, kind, days }) => (
          <li
            key={`${kind}-${app.id}`}
            className="flex flex-wrap items-center justify-between gap-2"
          >
            <span className="min-w-0">
              {kind === 'interview'
                ? `Interview at ${app.company_name} ${days === 0 ? 'today' : `in ${days} day${days > 1 ? 's' : ''}`}`
                : `${app.company_name}: no reply after ${days} days`}
            </span>
            <span className="flex flex-wrap gap-2">
              {kind === 'interview' ? (
                <Link to={`/tracker/${app.id}/prep`} className={buttonVariants({ size: 'sm' })}>
                  Prepare
                </Link>
              ) : (
                <Link
                  to={`/?${app.job_id ? `job=${app.job_id}&` : ''}ask=${encodeURIComponent(`Help me write a short follow-up email to ${app.company_name}${app.job_title ? ` about the ${app.job_title} role` : ''}. I applied ${days} days ago and have had no reply.`)}`}
                  className={buttonVariants({ size: 'sm', variant: 'outline' })}
                >
                  Draft a follow-up
                </Link>
              )}
              {kind === 'ghost' && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={change.isPending}
                  onClick={() => change.mutate({ id: app.id, status: 'ghosted' })}
                >
                  Mark as ghosted
                </Button>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
