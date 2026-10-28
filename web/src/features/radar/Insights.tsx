import { ArrowRight } from 'lucide-react'
import { useT, type Key } from '@/i18n'
import { useInsights } from './api'

const STEPS: [keyof NonNullable<ReturnType<typeof useInsights>['data']>['funnel'], Key][] = [
  ['scored', 'radar.i.scored'],
  ['shortlisted', 'radar.i.shortlisted'],
  ['approved', 'radar.i.approved'],
  ['applied', 'radar.i.applied'],
  ['interviews', 'radar.i.interviews'],
]

/** The radar's story over 30 days, and what keeps holding the user back. */
export function Insights() {
  const t = useT()
  const insights = useInsights()
  const data = insights.data
  if (!data || data.funnel.scored === 0) return null
  return (
    <section
      aria-label={t('radar.i.title', { days: data.days })}
      className="space-y-3 rounded-xl border bg-card p-4"
    >
      <h2 className="text-sm font-semibold">{t('radar.i.title', { days: data.days })}</h2>
      <ol className="flex flex-wrap items-center gap-2 text-sm">
        {STEPS.map(([key, label], i) => (
          <li key={key} className="flex items-center gap-2">
            {i > 0 && <ArrowRight className="size-3.5 text-muted-foreground" />}
            <span className={data.funnel[key] === 0 ? 'text-muted-foreground' : undefined}>
              {t(label)} <strong className="tabular-nums">{data.funnel[key]}</strong>
            </span>
          </li>
        ))}
        {data.average_score != null && (
          <li className="ml-auto text-muted-foreground">
            {t('radar.i.average', { score: Math.round(data.average_score) })}
          </li>
        )}
      </ol>
      {data.most_missing.length > 0 && (
        <div className="space-y-1">
          <p className="text-sm">
            <span className="font-medium">{t('radar.i.missing_title')}</span>{' '}
            <span className="text-muted-foreground">{t('radar.i.missing_hint')}</span>
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
