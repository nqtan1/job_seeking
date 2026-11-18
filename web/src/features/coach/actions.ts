import { useQuery, type QueryClient } from '@tanstack/react-query'
import { Bell, CircleAlert, CircleCheck } from 'lucide-react'
import type { ActionStatus, InboxMeta, ProposalMeta, StreamData } from './api'

/** How an inbox message looks, by kind (the chat row and Home). */
export const INBOX_KIND: Record<InboxMeta['kind'], { icon: typeof Bell; color: string }> = {
  run_done: { icon: CircleCheck, color: 'text-success' },
  run_failed: { icon: CircleAlert, color: 'text-destructive' },
  reminder: { icon: Bell, color: 'text-primary' },
}

/** A server-built app path, or null: never an outside or protocol-relative URL. */
export const appPath = (link: string | null | undefined) =>
  link?.startsWith('/') && !link.startsWith('//') ? link : null

/** A write the assistant proposed: it runs only when the user clicks "Confirm". */
export type ActionCardData = {
  action_id: string
  tool: string
  summary: string
  args: Record<string, string>
  untrusted: boolean
  status: ActionStatus
  code?: string | null
  result?: Record<string, string> | null // ids only once stored (run_id, flow_id), full in this session
}

/** A `proposal` SSE event → a pending card. */
export const cardFromEvent = (d: StreamData): ActionCardData => ({
  action_id: String(d.action_id),
  tool: String(d.tool),
  summary: String(d.summary ?? ''),
  args: (d.args as Record<string, string> | undefined) ?? {},
  untrusted: !!d.untrusted,
  status: 'pending',
})

/** The cards stored with an assistant message, each with its live status (`meta.actions`). */
export const cardsOf = (message: {
  meta?: { actions?: ProposalMeta[] } | null
}): ActionCardData[] => message.meta?.actions ?? []

type Live = Record<string, ActionCardData[]> // by assistant message id
const liveKey = (conversationId: string | undefined) => ['coach-actions', conversationId]

/** Cards proposed in this session, kept in the query cache so they outlive the remount from
 *  `/chat` to `/chat/:id` after a first reply, and keep their decided status. */
export function useLiveActions(conversationId: string | undefined): Live {
  // a cache-only entry: never fetched, so a refetch cannot wipe what saveLiveActions wrote
  return useQuery({
    queryKey: liveKey(conversationId),
    queryFn: (): Live => ({}),
    initialData: {},
    enabled: false,
  }).data
}

export function saveLiveActions(
  qc: QueryClient,
  conversationId: string,
  messageId: string,
  cards: ActionCardData[],
) {
  qc.setQueryData<Live>(liveKey(conversationId), (old = {}) => {
    const byId = new Map((old[messageId] ?? []).map((c) => [c.action_id, c]))
    for (const c of cards) byId.set(c.action_id, c)
    return { ...old, [messageId]: [...byId.values()] }
  })
}
