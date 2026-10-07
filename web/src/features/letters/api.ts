import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import { unwrap } from '@/lib/api/unwrap'
import type { components } from '@/lib/api/schema'

export type Letter = components['schemas']['LetterOut']
export type LetterIn = components['schemas']['LetterIn']
export type Block = 'subject' | 'salutation' | 'opening' | 'body' | 'closing'

export const useLetters = () =>
  useQuery({
    queryKey: ['letters'],
    queryFn: async () => unwrap(await api.GET('/api/v1/letters')),
  })

export const useLetter = (id: string) =>
  useQuery({
    queryKey: ['letter', id],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/letters/{letter_id}', { params: { path: { letter_id: id } } })),
  })

export function useDeleteLetter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) =>
      void unwrap(
        await api.DELETE('/api/v1/letters/{letter_id}', { params: { path: { letter_id: id } } }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['letters'] }),
  })
}

export function useCreateLetter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: LetterIn) => unwrap(await api.POST('/api/v1/letters', { body })),
    onSuccess: (l) => {
      qc.setQueryData(['letter', l.id], l)
      qc.invalidateQueries({ queryKey: ['letters'] })
    },
  })
}

export function useEditBlock(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (v: { block: Block; text: string; index?: number }) =>
      unwrap(
        await api.PATCH('/api/v1/letters/{letter_id}/blocks/{block}', {
          params: { path: { letter_id: id, block: v.block } },
          body: { text: v.text, index: v.index ?? null },
        }),
      ),
    onSuccess: (l) => qc.setQueryData(['letter', id], l),
  })
}

/** Start a render; the returned task id is polled with `useTask`. */
export const useRender = (id: string) =>
  useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/v1/letters/{letter_id}/render', {
          params: { path: { letter_id: id } },
        }),
      ),
  })

/**
 * Signed link to the rendered PDF. The server serves it inline under the letter's professional
 * name, so the iframe's own viewer (print, save) uses that name. Needs frame-src for the
 * storage origin in prod (P4-05).
 */
export function usePdfPreview(letterId: string, pdfDocumentId: string | null) {
  const link = useQuery({
    queryKey: ['letter-pdf', letterId, pdfDocumentId],
    enabled: !!pdfDocumentId,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/letters/{letter_id}/pdf', {
          params: { path: { letter_id: letterId } },
        }),
      ).download_url,
  })
  return { url: link.data, failed: link.isError }
}

export type AssistAction = components['schemas']['AssistIn']['action']

export const useAssist = (id: string) =>
  useMutation({
    mutationFn: async (v: { block: Block; selection: string; action: AssistAction }) =>
      unwrap(
        await api.POST('/api/v1/letters/{letter_id}/assist', {
          params: { path: { letter_id: id } },
          body: v,
        }),
      ),
  })

export const useVersions = (id: string) =>
  useQuery({
    queryKey: ['versions', id],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/letters/{letter_id}/versions', {
          params: { path: { letter_id: id } },
        }),
      ),
  })

export function useRestore(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (n: number) =>
      unwrap(
        await api.POST('/api/v1/letters/{letter_id}/versions/{n}/restore', {
          params: { path: { letter_id: id, n } },
        }),
      ),
    onSuccess: (l) => {
      qc.setQueryData(['letter', id], l)
      qc.invalidateQueries({ queryKey: ['versions', id] })
    },
  })
}

/** Grounding + quality check; only runs when asked (it can call the model). */
export const useCheck = (id: string) =>
  useQuery({
    queryKey: ['check', id],
    enabled: false,
    retry: false,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/letters/{letter_id}/check', { params: { path: { letter_id: id } } }),
      ),
  })

export const exportLetter = async (id: string, format: 'text' | 'email') =>
  unwrap(
    await api.GET('/api/v1/letters/{letter_id}/export', {
      params: { path: { letter_id: id }, query: { format } },
    }),
  )
