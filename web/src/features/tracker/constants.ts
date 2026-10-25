import type { Application, Status } from './api'

export const COLUMNS: [Status, string][] = [
  ['to_apply', 'To apply'],
  ['applied', 'Applied'],
  ['in_review', 'In review'],
  ['interview', 'Interview'],
  ['offer', 'Offer'],
  ['rejected', 'Rejected'],
  ['ghosted', 'Ghosted'],
]
export const LABEL = Object.fromEntries(COLUMNS) as Record<Status, string>

export const SOURCES = [
  'linkedin',
  'indeed',
  'france_travail',
  'referral',
  'company_site',
  'other',
] as const
export const sourceLabel = (s: string) => s.replace('_', ' ')

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
