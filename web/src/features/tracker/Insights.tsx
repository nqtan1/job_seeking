import { Link } from 'react-router'
import { useT } from '@/i18n'
import { askCoachUrl } from '@/features/coach/link'
import { StatusBadge } from '@/components/StatusBadge'
import { Button, buttonVariants } from '@/components/ui/button'
import { useChangeStatus, useFunnel, type Application } from './api'
import { needsAttention } from './attention'
import { sourceLabel } from './constants'

/** What works: replies and interviews by source, from the user's own tracker. */
export function Funnel() {
  const t = useT()
  const rows = useFunnel().data?.rows ?? []
  if (rows.length === 0) return null
  return (
    <details className="group rounded-xl border p-4">
      <summary className="cursor-pointer rounded text-sm font-semibold outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
        {t('tracker.funnel.title')}
      </summary>
      <ul aria-label={t('tracker.funnel.aria')} className="mt-2 space-y-1 text-sm">
        {rows.map((r) => (
          <li key={r.source} className="flex flex-wrap justify-between gap-2">
            <span className="first-letter:uppercase">{sourceLabel(t, r.source)}</span>
            <span className="text-muted-foreground">
              {t('tracker.funnel.sent', { count: r.sent })} ·{' '}
              {t('tracker.funnel.replied', { count: r.replied })} ·{' '}
              {t('tracker.funnel.interviews', { count: r.interviews })}
            </span>
          </li>
        ))}
      </ul>
    </details>
  )
}

/** "Needs attention": a follow-up to send, or an interview coming up. */
export function AttentionPanel({ apps }: { apps: Application[] }) {
  const t = useT()
  const change = useChangeStatus()
  const items = needsAttention(apps)
  if (items.length === 0) return null
  return (
    <section
      aria-label={t('tracker.attn.title')}
      className="space-y-2 rounded-xl border border-warning/40 bg-warning/10 p-4"
    >
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        {t('tracker.attn.title')} <StatusBadge tone="warning">{items.length}</StatusBadge>
      </h2>
      <ul className="space-y-2 text-sm">
        {items.map(({ app, kind, days }) => (
          <li
            key={`${kind}-${app.id}`}
            className="flex flex-wrap items-center justify-between gap-2"
          >
            <span className="min-w-0">
              {kind === 'interview'
                ? days === 0
                  ? t('tracker.attn.interview_today', { company: app.company_name })
                  : t('tracker.attn.interview_in', { company: app.company_name, count: days })
                : t('tracker.attn.no_reply', { company: app.company_name, days })}
            </span>
            <span className="flex flex-wrap gap-2">
              {kind === 'interview' ? (
                <Link to={`/tracker/${app.id}/prep`} className={buttonVariants({ size: 'sm' })}>
                  {t('tracker.attn.prepare')}
                </Link>
              ) : (
                <Link
                  to={askCoachUrl(
                    app.job_id,
                    app.job_title
                      ? t('tracker.attn.ask_role', {
                          company: app.company_name,
                          title: app.job_title,
                          days,
                        })
                      : t('tracker.attn.ask', { company: app.company_name, days }),
                  )}
                  className={buttonVariants({ size: 'sm', variant: 'outline' })}
                >
                  {t('tracker.attn.draft')}
                </Link>
              )}
              {kind === 'ghost' && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={change.isPending}
                  onClick={() => change.mutate({ id: app.id, status: 'ghosted' })}
                >
                  {t('tracker.attn.ghost')}
                </Button>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
