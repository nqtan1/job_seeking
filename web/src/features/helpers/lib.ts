import { useMemo } from 'react'
import { registerMessages, useT } from '@/i18n'
import type { Agent } from './api'
import type { AvatarSpec } from './avatar'
import type { Graph } from './graph'
import { helpers } from '@/i18n/messages/helpers'

/** Display names and characters for the steps. Wiring never reads these: a name can repeat or
 *  change without touching a connection. Two copies of one helper get "·2" so they stay apart. */
export function useLabels(graph: Graph | undefined, agents: Agent[] | undefined) {
  const t = useT()
  return useMemo(() => {
    const titles = new Map<string, string>()
    const avatars = new Map<string, AvatarSpec>()
    const seen = new Map<string, number>()
    for (const n of graph?.nodes ?? []) {
      if (n.type !== 'agent') {
        titles.set(n.id, t(`helpers.node.${n.type}`))
        continue
      }
      const a = agents?.find((x) => x.id === n.agent_id)
      const count = (seen.get(n.agent_id) ?? 0) + 1
      seen.set(n.agent_id, count)
      titles.set(n.id, `${a?.name ?? t('helpers.unavailable')}${count > 1 ? ` ·${count}` : ''}`)
      if (a) avatars.set(n.id, a.avatar)
    }
    return { titles, avatars }
  }, [graph, agents, t])
}

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

/** "1.2 s" under a minute, "2 min 5 s" beyond; "< 0.1 s" instead of a misleading "0.0 s". */
export function seconds(ms: number): string {
  if (ms < 100) return '< 0.1 s'
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`
  return `${Math.floor(ms / 60_000)} min ${Math.round((ms % 60_000) / 1000)} s`
}

/** An unsent draft survives a reload. Per-viewer convenience only: every access is guarded
 *  (private windows and blocked storage throw), and the page works without it. */
export function loadDraft<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

export function saveDraft(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* full or blocked: the draft is simply not kept */
  }
}

export function clearDraft(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    /* nothing to clear */
  }
}

/** Hover lift of a gallery card: moves only transform and shadow, and not at all when motion is reduced. */
export const LIFT =
  'transition-[transform,box-shadow] duration-200 ease-out hover:-translate-y-0.5 hover:shadow-md motion-reduce:transition-none motion-reduce:hover:translate-y-0'

// Imported by every Helpers page: the translations ship with the (lazy) pages, not the entry bundle.
registerMessages(helpers)
