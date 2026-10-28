import { useI18n } from '@/i18n'
import { useRuns, useSearches } from './api'
import { stopText, when } from './format'

/** What the radar did, as sentences. */
export function Timeline() {
  const { t, locale } = useI18n()
  const runs = useRuns()
  const searches = useSearches()
  if (!runs.data || runs.data.length === 0) return null
  const names = new Map((searches.data ?? []).map((s) => [s.id, s.name]))
  return (
    <section aria-label={t('radar.tl.title')} className="space-y-2">
      <h2 className="text-sm font-semibold text-muted-foreground">{t('radar.tl.title')}</h2>
      <ol className="space-y-1 text-sm">
        {runs.data.slice(0, 8).map((r) => (
          <li
            key={r.id}
            className={`flex flex-wrap justify-between gap-2 border-b py-1.5 ${r.status === 'ok' ? '' : 'text-warning'}`}
          >
            <span>
              <span className="text-muted-foreground">{when(r.started_at, t, locale)}</span>
              {' · '}
              {names.get(r.search_id) ?? t('radar.tl.fallback_name')}
            </span>
            <span className="text-muted-foreground">
              {r.scored > 0
                ? t('radar.tl.scored', { scored: r.scored, kept: r.shortlisted })
                : r.stop_reason === 'done'
                  ? r.found === 0
                    ? t('radar.tl.no_offers')
                    : t('radar.tl.all_seen', { count: r.found })
                  : t('radar.tl.nothing')}
              {r.stop_reason && r.stop_reason !== 'done' ? ` · ${stopText(t, r.stop_reason)}` : ''}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}
