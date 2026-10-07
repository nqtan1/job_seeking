import { useRadarStatus } from './api'

/** New matches, shown beside "Radar" in the menu so the user sees them without opening it. */
export function RadarBadge({ collapsed }: { collapsed?: boolean }) {
  const count = useRadarStatus().data?.new_matches ?? 0
  if (count === 0) return null
  return collapsed ? (
    <span aria-label={`${count} new matches`} className="size-2 rounded-full bg-primary" />
  ) : (
    <span
      aria-label={`${count} new matches`}
      className="ml-auto rounded-full bg-primary px-1.5 text-xs font-medium text-primary-foreground tabular-nums"
    >
      {count}
    </span>
  )
}
