import { catalogs, currentLang, tNow, type Key } from '@/i18n'
import type { components } from '@/lib/api/schema'

type Problem = components['schemas']['ProblemDetail']

/** User-facing text for an API error plus the request id, in the interface language. The
 *  backend's `detail` is English, so it is shown only when the interface is English; in French
 *  and Vietnamese the error `code` picks a translated message, never a mix of languages. */
export function describeError(error: unknown): string {
  const p = error as Partial<Problem> | undefined
  const key = `err.${p?.code ?? ''}`
  const text =
    currentLang() === 'en' && p?.detail
      ? p.detail
      : tNow((key in catalogs.en ? key : 'err.generic') as Key)
  return p?.request_id ? `${text} (${tNow('err.request_id', { id: p.request_id })})` : text
}
