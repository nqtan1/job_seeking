import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { track } from '@/lib/analytics'
import { api } from '@/lib/api/client'
import { getAppCheckHeaders } from '@/lib/app-check'
import { getAuthHeaders } from '@/lib/auth'
import type { components } from '@/lib/api/schema'
import { unwrap } from '@/lib/api/unwrap'

/** The user's chats: every conversation but the Assistant inbox (Home shows that one). */
export const useChats = () =>
  useQuery({
    queryKey: ['conversations'],
    queryFn: async () => unwrap(await api.GET('/api/v1/coach/conversations')),
    select: (list) => list.filter((c) => c.kind !== 'assistant'),
  })

export const useConversation = (id: string | undefined) =>
  useQuery({
    queryKey: ['conversation', id],
    enabled: !!id,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/coach/conversations/{conversation_id}', {
          params: { path: { conversation_id: id! } },
        }),
      ),
  })

/** Attach, switch (a job id) or detach (null) the job in focus. */
export function useSetFocus(id: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (jobId: string | null) =>
      unwrap(
        await api.PATCH('/api/v1/coach/conversations/{conversation_id}', {
          params: { path: { conversation_id: id! } },
          body: { job_id: jobId },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conversation', id] }),
  })
}

export function useDeleteConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.DELETE('/api/v1/coach/conversations/{conversation_id}', {
          params: { path: { conversation_id: id } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['conversations'] }),
  })
}

export const useMessages = (id: string | undefined) =>
  useQuery({
    queryKey: ['messages', id],
    enabled: !!id,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/coach/conversations/{conversation_id}/messages', {
          params: { path: { conversation_id: id! } },
        }),
      ),
  })

/** A new chat, focused on a job and/or with a helper (null: the default coach). */
export const createConversation = async (body: {
  job_id: string | null
  agent_id: string | null
}) => unwrap(await api.POST('/api/v1/coach/conversations', { body }))

export type Citation = components['schemas']['Citation']
export type ProposalMeta = components['schemas']['ProposalMeta']
export type InboxMeta = components['schemas']['InboxMeta']
export type StreamData = Record<string, unknown>
export type OnEvent = (name: string, data: StreamData) => void

const post = async (path: string, body: unknown, signal?: AbortSignal) =>
  fetch(path, {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
      ...(await getAuthHeaders()),
      ...(await getAppCheckHeaders()),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

/** POST and read the Server-Sent Events reply, calling `onEvent` for each event (`context`,
 *  `step`, `token`, `citations`, `suggestions`, `notice`, `done`). Throws the problem+json body
 *  for a refusal before the first event, or `{detail, request_id}` for an `error` event (both
 *  render through `describeError`). */
async function stream(path: string, body: unknown, onEvent: OnEvent, signal?: AbortSignal) {
  const res = await post(path, body, signal)
  if (!res.ok || !res.body) throw await res.json().catch(() => ({}))

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) return
    buffer += value
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const name = /^event: (.*)$/m.exec(block)?.[1]
      if (!name) continue // a `: ping` heartbeat
      const data = JSON.parse(/^data: (.*)$/m.exec(block)?.[1] ?? '{}') as StreamData
      if (name === 'error') throw { detail: data.detail, request_id: data.request_id }
      onEvent(name, data)
      if (name === 'done') return
    }
  }
}

export const streamMessage = (
  conversationId: string,
  content: string,
  onEvent: OnEvent,
  signal?: AbortSignal,
) =>
  stream(
    `/api/v1/coach/conversations/${conversationId}/messages`,
    { content },
    onEvent,
    signal,
  ).then(() => track('chat_sent'))

/** Re-answer the last message; the new reply replaces the old one. */
export const regenerateReply = (conversationId: string, onEvent: OnEvent, signal?: AbortSignal) =>
  stream(`/api/v1/coach/conversations/${conversationId}/regenerate`, undefined, onEvent, signal)

/** Where a proposed action stands, as its card shows it (a UI state, not an API type). */
export type ActionStatus = 'pending' | 'done' | 'cancelled' | 'failed' | 'expired'

/** Confirm or cancel an action the chat proposed. A 410 means it expired; any other refusal
 *  (409: already decided) is a failure with its problem code. `result` holds the tool's outputs
 *  (e.g. `run_id`, `flow_id`) once done. */
export async function decideAction(
  conversationId: string,
  actionId: string,
  decision: 'confirm' | 'cancel',
): Promise<{ status: ActionStatus; code: string | null; result?: Record<string, string> | null }> {
  const { data, error, response } = await api.POST(
    '/api/v1/coach/conversations/{conversation_id}/actions/{action_id}',
    {
      params: { path: { conversation_id: conversationId, action_id: actionId } },
      body: { decision },
    },
  )
  if (data) return { status: data.status, code: data.code ?? null, result: data.result }
  if (response.status === 410) return { status: 'expired', code: 'expired' }
  if (response.status === 409) return { status: 'failed', code: 'decided' }
  return { status: 'failed', code: error && 'code' in error ? error.code : null }
}
