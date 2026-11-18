const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 31_536_000],
  ['month', 2_592_000],
  ['day', 86_400],
  ['hour', 3_600],
  ['minute', 60],
]

/** "3 hours ago", in the interface language. Falls back to "now" under a minute. */
export function relTime(iso: string, locale: string, now = Date.now()): string {
  const secs = Math.round((new Date(iso).getTime() - now) / 1000)
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  for (const [unit, size] of UNITS) {
    if (Math.abs(secs) >= size) return rtf.format(Math.round(secs / size), unit)
  }
  return rtf.format(0, 'second')
}

/** A date and time in the interface language ("" when unknown). */
export const when = (iso: string | null, locale: string) =>
  iso ? new Date(iso).toLocaleString(locale) : ''
