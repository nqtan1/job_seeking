import { Check, Circle } from 'lucide-react'
import { Link } from 'react-router'
import { useJobs } from '@/features/job-search/api'
import { useMe } from '@/features/settings/api'
import { cn } from 'cn'
import { useAllFits } from './api'
import { useLetters } from '@/features/letters/api'
import { useSearches } from '@/features/radar/api'
import { useApplications } from '@/features/tracker/api'

/** "Your next steps": the whole journey on one card, shown until every step is done. */
export function Checklist() {
  const me = useMe()
  const jobs = useJobs()
  const fits = useAllFits()
  const letters = useLetters()
  const apps = useApplications()
  const radars = useSearches()
  const steps = [
    { label: 'Add your CV', to: '/profile', done: !!me.data?.onboarding.has_profile },
    { label: 'Add a job you like', to: '/jobs', done: (jobs.data?.length ?? 0) > 0 },
    { label: 'Check how well you fit', to: '/jobs', done: (fits.data?.length ?? 0) > 0 },
    { label: 'Write a cover letter', to: '/letters', done: (letters.data?.length ?? 0) > 0 },
    { label: 'Track an application', to: '/tracker', done: (apps.data?.length ?? 0) > 0 },
    {
      label: 'Let the radar find jobs for you',
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
      aria-label="Next steps"
      className="mx-auto max-w-xl rounded-xl border bg-card p-4 text-left shadow-xs"
    >
      <p className="mb-2 text-sm font-semibold">
        Your next steps{' '}
        <span className="font-normal text-muted-foreground">
          ({done} of {steps.length})
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
