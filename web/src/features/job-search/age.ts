const DAY = 86_400_000
const STALE_AFTER_DAYS = 30

/** Days since the provider's posting date, or null when unknown. Heuristic: old != fake. */
export function postingAgeDays(postedOn: string | null | undefined, now = new Date()) {
  if (!postedOn) return null
  const t = new Date(postedOn).getTime()
  return Number.isNaN(t) ? null : Math.max(0, Math.floor((now.getTime() - t) / DAY))
}

export const isStale = (days: number | null) => days !== null && days >= STALE_AFTER_DAYS
