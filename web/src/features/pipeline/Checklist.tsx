import { Check, Circle } from 'lucide-react'
import { Link } from 'react-router'
import { useT } from '@/i18n'
import { useJobs } from '@/features/job-search/api'
import { useMe } from '@/features/settings/api'
import { cn } from 'cn'
import { useAllFits } from './api'
import { useLetters } from '@/features/letters/api'
import { useSearches } from '@/features/radar/api'
import { useApplications } from '@/features/tracker/api'

/** "Your next steps": the whole journey on one card, shown until every step is done. */
export function Checklist() {
  const t = useT()
  const me = useMe()
  const jobs = useJobs()
  const fits = useAllFits()
  const letters = useLetters()
  const apps = useApplications()
  const radars = useSearches()
  const steps = [
    { label: t('pipeline.step.cv'), to: '/profile', done: !!me.data?.onboarding.has_profile },
    { label: t('pipeline.step.job'), to: '/jobs', done: (jobs.data?.length ?? 0) > 0 },
    { label: t('pipeline.step.fit'), to: '/jobs', done: (fits.data?.length ?? 0) > 0 },
    { label: t('pipeline.step.letter'), to: '/letters', done: (letters.data?.length ?? 0) > 0 },
    { label: t('pipeline.step.track'), to: '/tracker', done: (apps.data?.length ?? 0) > 0 },
    {
      label: t('pipeline.step.radar'),
      to: '/radar',
      done: (radars.data?.length ?? 0) > 0,
    },
  ]
  const loading = [me, jobs, fits, letters, apps, radars].some((q) => q.isPending)
  const done = steps.filter((s) => s.done).length
  if (loading || done === steps.length) return null
  const next = steps.findIndex((s) => !s.done)
  return (
    <section
      aria-label={t('pipeline.next_aria')}
      className="mx-auto max-w-xl rounded-xl border bg-card p-4 text-left shadow-xs"
    >
      <p className="mb-2 text-sm font-semibold">
        {t('pipeline.next')}{' '}
        <span className="font-normal text-muted-foreground">
          {t('pipeline.progress', { done, total: steps.length })}
        </span>
      </p>
      <ol className="space-y-1">
        {steps.map((s, i) => (
          <li key={s.label}>
            <Link
              to={s.to}
              className={cn(
                'flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-accent',
                s.done && 'text-muted-foreground line-through',
                i === next && 'bg-accent/60 font-medium',
              )}
            >
              {s.done ? <Check className="size-4 text-success" /> : <Circle className="size-4" />}
              {s.label}
            </Link>
          </li>
        ))}
      </ol>
    </section>
  )
}
