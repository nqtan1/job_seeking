import type { Key, useT } from '@/i18n'
import type { Application, Status } from './api'

export type T = ReturnType<typeof useT>

/** Board columns in order; the label is looked up with `t(STATUS_KEY[status])`. */
export const COLUMNS: Status[] = [
  'to_apply',
  'applied',
  'in_review',
  'interview',
  'offer',
  'rejected',
  'ghosted',
]
export const STATUS_KEY = Object.fromEntries(
  COLUMNS.map((s) => [s, `tracker.status.${s}`]),
) as Record<Status, Key>

export const SOURCES = [
  'linkedin',
  'indeed',
  'france_travail',
  'referral',
  'company_site',
  'other',
] as const
export const sourceLabel = (t: T, s: string) =>
  (SOURCES as readonly string[]).includes(s) ? t(`tracker.source.${s}` as Key) : s.replace('_', ' ')

export const DOT: Record<Status, string> = {
  to_apply: 'bg-muted-foreground',
  applied: 'bg-primary',
  in_review: 'bg-warning',
  interview: 'bg-chart-2',
  offer: 'bg-success',
  rejected: 'bg-destructive',
  ghosted: 'bg-muted-foreground/50',
}

export const TONE: Record<Status, 'neutral' | 'info' | 'success' | 'warning' | 'danger'> = {
  to_apply: 'neutral',
  applied: 'info',
  in_review: 'warning',
  interview: 'info',
  offer: 'success',
  rejected: 'danger',
  ghosted: 'neutral',
}

/** Company first (the thing you recognise), role second. */
export const appName = (a: Pick<Application, 'company_name' | 'job_title'>) =>
  a.job_title ? `${a.company_name} — ${a.job_title}` : a.company_name

/** `<input type="datetime-local">` wants local time without a zone: "2026-10-20T14:00". */
export const toLocalInput = (iso: string | null) => {
  if (!iso) return ''
  const d = new Date(iso)
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
