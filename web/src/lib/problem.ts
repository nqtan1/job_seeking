import type { components } from '@/lib/api/schema'

type Problem = components['schemas']['ProblemDetail']

/** User-facing text for an API error: the backend's own safe `detail` plus the request id. */
export function describeError(error: unknown): string {
  const p = error as Partial<Problem> | undefined
  if (!p?.detail) return 'Something went wrong. Please try again.'
  return p.request_id ? `${p.detail} (request id: ${p.request_id})` : p.detail
}
