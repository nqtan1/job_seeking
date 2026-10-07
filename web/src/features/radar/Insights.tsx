import { ArrowRight } from 'lucide-react'
import { useInsights } from './api'

const STEPS: [keyof NonNullable<ReturnType<typeof useInsights>['data']>['funnel'], string][] = [
  ['scored', 'Looked at'],
  ['shortlisted', 'Kept'],
  ['approved', 'You approved'],
  ['applied', 'Applied to'],
  ['interviews', 'Interviews'],
]

/** The radar's story over 30 days, and what keeps holding the user back. */
export function Insights() {
  const insights = useInsights()
  const data = insights.data
  if (!data || data.funnel.scored === 0) return null
  return (
    <section aria-label="Your last 30 days" className="space-y-3 rounded-xl border bg-card p-4">
      <h2 className="text-sm font-semibold">Your last {data.days} days</h2>
      <ol className="flex flex-wrap items-center gap-2 text-sm">
        {STEPS.map(([key, label], i) => (
          <li key={key} className="flex items-center gap-2">
            {i > 0 && <ArrowRight className="size-3.5 text-muted-foreground" />}
            <span className={data.funnel[key] === 0 ? 'text-muted-foreground' : undefined}>
              {label} <strong className="tabular-nums">{data.funnel[key]}</strong>
            </span>
          </li>
        ))}
        {data.average_score != null && (
          <li className="ml-auto text-muted-foreground">
            average fit {Math.round(data.average_score)}%
          </li>
        )}
      </ol>
      {data.most_missing.length > 0 && (
        <div className="space-y-1">
          <p className="text-sm">
            <span className="font-medium">Missing most often:</span>{' '}
            <span className="text-muted-foreground">
              if you have these, add them to your CV; if not, they are worth learning.
            </span>
          </p>
          <ul className="flex flex-wrap gap-2">
            {data.most_missing.map((m) => (
              <li
                key={m.text}
                className="rounded-full bg-warning/15 px-2.5 py-0.5 text-xs text-warning"
              >
                {m.text} ×{m.count}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
