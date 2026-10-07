import { useRuns, useSearches } from './api'
import { STOP, when } from './format'

/** What the radar did, as sentences. */
export function Timeline() {
  const runs = useRuns()
  const searches = useSearches()
  if (!runs.data || runs.data.length === 0) return null
  const names = new Map((searches.data ?? []).map((s) => [s.id, s.name]))
  return (
    <section aria-label="What your radar did" className="space-y-2">
      <h2 className="text-sm font-semibold text-muted-foreground">What your radar did</h2>
      <ol className="space-y-1 text-sm">
        {runs.data.slice(0, 8).map((r) => (
          <li
            key={r.id}
            className={`flex flex-wrap justify-between gap-2 border-b py-1.5 ${r.status === 'ok' ? '' : 'text-warning'}`}
          >
            <span>
              <span className="text-muted-foreground">{when(r.started_at)}</span>
              {' · '}
              {names.get(r.search_id) ?? 'Radar'}
            </span>
            <span className="text-muted-foreground">
              {r.scored > 0
                ? `looked at ${r.scored} new, kept ${r.shortlisted}`
                : r.stop_reason === 'done'
                  ? r.found === 0
                    ? 'found no offers: try broader keywords'
                    : `nothing new: all ${r.found} offers were already seen`
                  : 'nothing looked at'}
              {r.stop_reason && r.stop_reason !== 'done' ? ` · ${STOP[r.stop_reason]}` : ''}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}
