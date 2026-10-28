import { CircleAlert } from 'lucide-react'
import { describeError } from '@/lib/problem'

/** Renders nothing when `error` is empty. The one way an API error reaches the user: safe message + request id, announced as an alert. */
export function ErrorMessage({ error }: { error: unknown | null | undefined }) {
  if (!error) return null
  return (
    <p
      role="alert"
      className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
    >
      <CircleAlert className="mt-0.5 size-4 shrink-0" />
      {describeError(error)}
    </p>
  )
}
