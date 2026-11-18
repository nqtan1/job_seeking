import { useMutation, useQueryClient } from '@tanstack/react-query'
import { TriangleAlert } from 'lucide-react'
import { useId } from 'react'
import { Link } from 'react-router'
import { StatusBadge } from '@/components/StatusBadge'
import { Button, buttonVariants } from '@/components/ui/button'
import { catalogs, useI18n, type Key } from '@/i18n'
import { cn } from 'cn'
import { decideAction, type InboxMeta } from './api'
import {
  INBOX_KIND,
  appPath,
  cardsOf,
  saveLiveActions,
  useLiveActions,
  type ActionCardData,
} from './actions'

type T = ReturnType<typeof useI18n>['t']
const has = (key: string) => key in catalogs.en

const TONE = {
  pending: 'neutral',
  done: 'success',
  cancelled: 'neutral',
  expired: 'warning',
  failed: 'danger',
} as const

/** "07:00" or "07:00 AM", as the interface language writes an hour of the day. */
const atHour = (hour: string, locale: string) =>
  new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }).format(
    new Date(2000, 0, 1, Number(hour) || 0),
  )

/** A job hunter's schedule in plain words; the server's defaults when the model left them out. */
function schedule(t: T, locale: string, card: ActionCardData) {
  if (card.tool !== 'set_up_job_hunter') return null
  const time = atHour(card.args.hour ?? '8', locale)
  return t('coach.action.schedule', { time, fit: card.args.min_fit ?? '60' })
}

/** Where a done flow action leads: the run it started, or the flow it set up. */
function doneLink(card: ActionCardData) {
  const r = card.status === 'done' ? card.result : null
  if (card.tool === 'run_routine' && r?.run_id)
    return { to: `/automations/runs/${encodeURIComponent(r.run_id)}`, key: 'coach.action.open_run' }
  if (card.tool === 'set_up_job_hunter' && r?.flow_id)
    return { to: `/automations/${encodeURIComponent(r.flow_id)}`, key: 'coach.action.open_flow' }
  return null
}

/** Why a failed or expired action did not run (a known problem code, else a generic line). */
function reason(t: T, card: ActionCardData) {
  if (card.status === 'expired') return t('coach.action.code.expired')
  if (card.status !== 'failed') return null
  const key = `coach.action.code.${card.code}`
  return t((has(key) ? key : 'coach.action.code.generic') as Key)
}

/** One argument as people read it: a time, a score, a tracker status, else the text itself. */
function argValue(t: T, locale: string, name: string, value: string) {
  if (name === 'hour') return atHour(value, locale)
  if (name === 'min_fit') return `${value}/100`
  if (name === 'status' && has(`tracker.status.${value}`))
    return t(`tracker.status.${value}` as Key)
  return value
}

/** Every value the action runs with, in full (the summary may be short). The schedule line
 *  already says a job hunter's hour and fit. */
function Details({ card }: { card: ActionCardData }) {
  const { t, locale } = useI18n()
  const hidden = card.tool === 'set_up_job_hunter' ? ['hour', 'min_fit'] : []
  const shown = Object.entries(card.args).filter(([k]) => !k.endsWith('_id') && !hidden.includes(k))
  if (shown.length === 0) return null
  const label = (k: string) => {
    const key = `coach.action.arg.${k}`
    if (has(key)) return t(key as Key)
    const words = k.replace(/_/g, ' ')
    return words.charAt(0).toUpperCase() + words.slice(1)
  }
  return (
    <details className="text-muted-foreground">
      <summary className="cursor-pointer text-xs select-none">{t('coach.action.details')}</summary>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        {shown.map(([k, v]) => (
          <div key={k} className="contents">
            <dt>{label(k)}</dt>
            <dd className="min-w-0 break-words whitespace-pre-wrap text-foreground">
              {argValue(t, locale, k, v)}
            </dd>
          </div>
        ))}
      </dl>
    </details>
  )
}

/** One suggested action: what it will do, a warning when outside content suggested it, and the
 *  one primary button. `conversationId` is absent while the first reply still streams. */
export function ActionCard({
  card,
  conversationId,
  messageId,
}: {
  card: ActionCardData
  conversationId?: string
  messageId?: string
}) {
  const { t, locale } = useI18n()
  const id = useId()
  const qc = useQueryClient()
  const decide = useMutation({
    mutationFn: (decision: 'confirm' | 'cancel') =>
      decideAction(conversationId!, card.action_id, decision),
    onSuccess: async (next) => {
      if (messageId) saveLiveActions(qc, conversationId!, messageId, [{ ...card, ...next }])
      // a confirmed action adds a short "Done: …" reply on the server
      await qc.invalidateQueries({ queryKey: ['messages', conversationId] })
    },
    onError: () =>
      messageId &&
      saveLiveActions(qc, conversationId!, messageId, [{ ...card, status: 'failed', code: null }]),
  })
  const running = decide.isPending
  const ready = !!conversationId && !!messageId
  const why = reason(t, card)
  const when = schedule(t, locale, card)
  const link = doneLink(card)
  return (
    <section
      aria-labelledby={`${id}-kind ${id}-summary`}
      className="max-w-[85%] space-y-2 rounded-xl border bg-card p-3 text-sm shadow-xs"
    >
      <div className="flex items-start gap-2">
        <span id={`${id}-kind`} className="sr-only">
          {t('coach.action.label')}
        </span>
        <p id={`${id}-summary`} className="min-w-0 flex-1 font-medium break-words">
          {card.summary}
        </p>
        <span role="status">
          <StatusBadge tone={TONE[card.status]}>
            {t(`coach.action.status.${card.status}`)}
          </StatusBadge>
        </span>
      </div>
      {card.untrusted && (
        <p role="note" className="flex gap-2 rounded-lg bg-warning/10 p-2 text-warning">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          {t('coach.action.untrusted')}
        </p>
      )}
      {when && <p className="text-muted-foreground">{when}</p>}
      <Details card={card} />
      {why && <p className="text-muted-foreground">{why}</p>}
      {card.status === 'pending' && (
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            loading={running}
            disabled={!ready}
            onClick={() => decide.mutate('confirm')}
          >
            {t('coach.action.confirm')}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={running || !ready}
            onClick={() => decide.mutate('cancel')}
          >
            {t('coach.action.cancel')}
          </Button>
        </div>
      )}
      {link && (
        <Link to={link.to} className={buttonVariants({ variant: 'outline', size: 'sm' })}>
          {t(link.key as Key)}
        </Link>
      )}
    </section>
  )
}

/** The cards of one assistant message: stored ones, overridden by this session's live state. */
export function ActionCards({
  conversationId,
  message,
}: {
  conversationId: string | undefined
  message: { id: string } & Parameters<typeof cardsOf>[0]
}) {
  const live = useLiveActions(conversationId)
  const byId = new Map(cardsOf(message).map((c) => [c.action_id, c]))
  for (const c of live[message.id] ?? []) byId.set(c.action_id, c)
  return [...byId.values()].map((c) => (
    <ActionCard key={c.action_id} card={c} conversationId={conversationId} messageId={message.id} />
  ))
}

/** Something the app posted to the Assistant chat (a run finished, a reminder): a compact row,
 *  not a reply. The text is server-built; shown as plain text. */
export function InboxRow({ inbox, text }: { inbox: InboxMeta; text: string }) {
  const { t } = useI18n()
  const kind = INBOX_KIND[inbox.kind] ?? INBOX_KIND.reminder // a kind this build does not know
  const link = appPath(inbox.link)
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-sm">
      <kind.icon className={cn('size-4', kind.color)} aria-hidden />
      <p className="min-w-0 flex-1 break-words">{text}</p>
      {link && (
        <Link to={link} className={buttonVariants({ variant: 'outline', size: 'sm' })}>
          {t('coach.inbox.open')}
        </Link>
      )}
    </div>
  )
}
