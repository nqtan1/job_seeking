// audit: keep-separate (Home and the tracker import it without loading the chat page)
/** The longest message the chat accepts (the composer and Home's ask box). */
export const MAX_MESSAGE = 4000

/** Assistant deep link: opens the chat (about `jobId` if any) with `text` prefilled for review. */
export const askCoachUrl = (jobId: string | null | undefined, text: string) =>
  `/chat?${jobId ? `job=${jobId}&` : ''}draft=${encodeURIComponent(text)}`
