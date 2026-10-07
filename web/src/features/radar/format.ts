const time = (d: Date) => d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

const dayDiff = (d: Date, now: Date) => {
  const start = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  return Math.round((start(d) - start(now)) / 86_400_000)
}

/** "today 08:30", "yesterday 08:30", "tomorrow 08:30", else "12 Oct 08:30" (the user's own clock). */
export function when(iso: string, now = new Date()): string {
  const d = new Date(iso)
  const diff = dayDiff(d, now)
  const day =
    diff === 0
      ? 'today'
      : diff === 1
        ? 'tomorrow'
        : diff === -1
          ? 'yesterday'
          : d.toLocaleDateString([], { day: 'numeric', month: 'short' })
  return `${day} ${time(d)}`
}

/** "today", "yesterday" or the date: for when a match was found. */
export function foundOn(iso: string, now = new Date()): string {
  const diff = dayDiff(new Date(iso), now)
  return diff === 0
    ? 'found today'
    : diff === -1
      ? 'found yesterday'
      : `found ${new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short' })}`
}

export const STOP: Record<string, string> = {
  done: 'finished',
  limit: 'stopped at your daily limit',
  quota: 'paused to keep some of your daily AI use free',
  no_profile: 'needs your CV first',
  ai_unavailable: 'the AI was unavailable',
  provider_error: 'the job source was unavailable',
  stalled: 'the run did not finish',
  worker_stopped: 'the run was cut off when the worker stopped',
  invalid_search: 'the place or contract could not be used: edit this radar',
  internal_error: 'something went wrong',
}
