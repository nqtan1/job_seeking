import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import { getAppCheckHeaders } from '@/lib/app-check'
import { getAuthHeaders } from '@/lib/auth'
import { unwrap } from '@/lib/api/unwrap'

export const useConversations = () =>
  useQuery({
    queryKey: ['conversations'],
    queryFn: async () => unwrap(await api.GET('/api/v1/coach/conversations')),
  })

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

export const createConversation = async (jobId?: string) =>
  unwrap(await api.POST('/api/v1/coach/conversations', { body: { job_id: jobId ?? null } }))

/** POST a message and read the Server-Sent Events reply, calling `onToken` for each chunk.
 *  Throws the problem+json body for a refusal before the first token, or `{detail}` for an
 *  `error` event in the stream (both render through `describeError`). */
export async function streamMessage(
  conversationId: string,
  content: string,
  onToken: (text: string) => void,
  signal?: AbortSignal,
) {
  const res = await fetch(`/api/v1/coach/conversations/${conversationId}/messages`, {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
      ...(await getAuthHeaders()),
      ...(await getAppCheckHeaders()),
    },
    body: JSON.stringify({ content }),
  })
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
      const event = /^event: (.*)$/m.exec(block)?.[1]
      const data = JSON.parse(/^data: (.*)$/m.exec(block)?.[1] ?? '{}') as {
        text?: string
        detail?: string
      }
      if (event === 'token') onToken(data.text ?? '')
      else if (event === 'error') throw { detail: data.detail }
      else if (event === 'done') return
    }
  }
}
