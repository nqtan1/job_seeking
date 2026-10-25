import { CalendarClock, TriangleAlert } from 'lucide-react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { cn } from 'cn'
import { useChangeStatus, type Application, type Status } from './api'
import type { Attention } from './attention'
import { LABEL, appName, sourceLabel } from './constants'

const fmt = (iso: string, opts: Intl.DateTimeFormatOptions) =>
  new Date(iso).toLocaleDateString([], opts)

/** The forward step worth a one-tap button; rejected/ghosted stay in the "Other" menu. */
const FORWARD = (s: Status) => s !== 'rejected' && s !== 'ghosted' && s !== 'to_apply'

function cue(a: Attention) {
  if (a.kind === 'interview')
    return {
      text: a.days === 0 ? 'Interview today' : `Interview in ${a.days} d`,
      tone: 'warning' as const,
    }
  if (a.kind === 'ghost') return { text: `No reply · ${a.days} d`, tone: 'danger' as const }
  return { text: `Follow up · ${a.days} d`, tone: 'warning' as const }
}

/**
 * Compact card: who (company, role), when/where (one meta line), what next (one button).
 * Everything else lives in the drawer, opened by the card body.
 */
export function ApplicationCard({
  app,
  attention,
  onOpen,
}: {
  app: Application
  attention?: Attention
  onOpen: () => void
}) {
  const change = useChangeStatus()
  const name = appName(app)
  const forward = app.next_statuses.find(FORWARD)
  const others = app.next_statuses.filter((s) => s !== forward)
  const meta = [
    sourceLabel(app.source),
    app.location,
    app.applied_at && `Applied ${fmt(app.applied_at, { month: 'short', day: 'numeric' })}`,
  ].filter(Boolean)
  const flag = attention && cue(attention)
  return (
    <li
      draggable
      onDragStart={(e) => e.dataTransfer.setData('text/plain', app.id)}
      className={cn(
        'space-y-2 rounded-lg border bg-card p-3 text-sm shadow-xs md:cursor-grab md:active:cursor-grabbing',
        flag && 'border-warning/50',
      )}
    >
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Open ${name}`}
        className="block w-full space-y-1 rounded-md text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <span className="block truncate font-medium">{app.company_name}</span>
        {app.job_title && (
          <span className="block truncate text-muted-foreground">{app.job_title}</span>
        )}
        <span className="block text-xs text-muted-foreground capitalize">{meta.join(' · ')}</span>
        {app.interview_at && (
          <span className="flex items-center gap-1 text-xs font-medium text-primary">
            <CalendarClock className="size-3.5" aria-hidden />
            {new Date(app.interview_at).toLocaleString([], {
              dateStyle: 'medium',
              timeStyle: 'short',
            })}
          </span>
        )}
      </button>
      {flag && (
        <StatusBadge tone={flag.tone}>
          <TriangleAlert className="mr-1 size-3" aria-hidden />
          {flag.text}
        </StatusBadge>
      )}
      {app.next_statuses.length > 0 && (
        <div className="flex items-center gap-2">
          {forward && (
            <Button
              size="sm"
              disabled={change.isPending}
              onClick={() => change.mutate({ id: app.id, status: forward })}
            >
              Move to {LABEL[forward]}
            </Button>
          )}
          {others.length > 0 && (
            <NativeSelect
              size="sm"
              aria-label={`Move ${name}`}
              className="min-w-0 flex-1"
              value=""
              disabled={change.isPending}
              onChange={(e) => change.mutate({ id: app.id, status: e.target.value as Status })}
            >
              <NativeSelectOption value="" disabled>
                {forward ? 'Other…' : 'Move to…'}
              </NativeSelectOption>
              {others.map((s) => (
                <NativeSelectOption key={s} value={s}>
                  {LABEL[s]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          )}
        </div>
      )}
      {change.isError && <ErrorMessage error={change.error} />}
    </li>
  )
}
