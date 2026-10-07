/** An openapi-fetch result → its data, or throw its problem+json error (shown via `describeError`). */
export function unwrap<T>(result: { data?: T; error?: unknown }): T {
  if (result.error) throw result.error
  return result.data as T
}
