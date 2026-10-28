/** Coach deep link: opens the chat (about `jobId` if any) with `text` prefilled for review. */
export const askCoachUrl = (jobId: string | null | undefined, text: string) =>
  `/?${jobId ? `job=${jobId}&` : ''}ask=${encodeURIComponent(text)}`
