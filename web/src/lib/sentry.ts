import type { ErrorEvent } from '@sentry/react'

const noQuery = (v: unknown) => (typeof v === 'string' ? v.split(/[?#]/)[0] : undefined)

/** Nothing personal leaves the browser (ADR 0040): no request, user, message text or query
 *  strings; the exception type and stack stay. */
export function scrub(event: ErrorEvent): ErrorEvent {
  delete event.request
  delete event.user
  delete event.message
  delete event.extra
  event.exception?.values?.forEach((e) => delete e.value)
  event.breadcrumbs = event.breadcrumbs?.map(({ category, type, level, timestamp, data }) => ({
    category,
    type,
    level,
    timestamp,
    data: data && { url: noQuery(data.url), from: noQuery(data.from), to: noQuery(data.to) },
  }))
  return event
}

/** Off unless the build sets `VITE_SENTRY_DSN` (empty in dev, tests and CI). Loaded on demand to
 *  keep the SDK out of the first bundle; an error in the first moments before it loads is missed. */
export async function initSentry() {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (!dsn) return
  const Sentry = await import('@sentry/react')
  Sentry.init({
    dsn,
    release: import.meta.env.VITE_SENTRY_RELEASE || undefined,
    // v11's `sendDefaultPii: false`: collect no user, cookies, headers, query or bodies.
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
    },
    beforeSend: scrub,
  })
}

/** Report one error (a no-op while Sentry is off). */
export const report = (error: unknown, requestId?: string) =>
  void import('@sentry/react').then((s) =>
    s.captureException(error, requestId ? { tags: { request_id: requestId } } : undefined),
  )
