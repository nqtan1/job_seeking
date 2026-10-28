import type { Key, Vars } from '@/i18n'

export type Tr = (key: Key, vars?: Vars) => string

const dayDiff = (d: Date, now: Date) => {
  const start = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  return Math.round((start(d) - start(now)) / 86_400_000)
}
const shortDate = (d: Date, locale: string) =>
  d.toLocaleDateString(locale, { day: 'numeric', month: 'short' })

/** "today 08:30", "yesterday 08:30", "tomorrow 08:30", else "12 Oct 08:30" (the user's own clock). */
export function when(iso: string, t: Tr, locale: string, now = new Date()): string {
  const d = new Date(iso)
  const diff = dayDiff(d, now)
  const day =
    diff === 0
      ? t('radar.today')
      : diff === 1
        ? t('radar.tomorrow')
        : diff === -1
          ? t('radar.yesterday')
          : shortDate(d, locale)
  return `${day} ${d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}`
}

/** "found today", "found yesterday" or the date: for when a match was found. */
export function foundOn(iso: string, t: Tr, locale: string, now = new Date()): string {
  const d = new Date(iso)
  const diff = dayDiff(d, now)
  return diff === 0
    ? t('radar.found_today')
    : diff === -1
      ? t('radar.found_yesterday')
      : t('radar.found_on', { date: shortDate(d, locale) })
}

const STOP_KEYS: Record<string, Key> = {
  done: 'radar.stop.done',
  limit: 'radar.stop.limit',
  quota: 'radar.stop.quota',
  no_profile: 'radar.stop.no_profile',
  ai_unavailable: 'radar.stop.ai_unavailable',
  provider_error: 'radar.stop.provider_error',
  stalled: 'radar.stop.stalled',
  worker_stopped: 'radar.stop.worker_stopped',
  invalid_search: 'radar.stop.invalid_search',
  internal_error: 'radar.stop.internal_error',
}

/** Why a run stopped, in words; unknown codes read as a generic failure. */
export const stopText = (t: Tr, reason: string) =>
  t(STOP_KEYS[reason] ?? 'radar.stop.internal_error')
