import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { unwrap } from '@/lib/api/unwrap'

export type Signature = components['schemas']['SignatureOut']
const KEY = ['signature']

/** `null` = nothing stored. The signed image URL is short-lived, so it is refetched often. */
export const useSignature = () =>
  useQuery({
    queryKey: KEY,
    staleTime: 60_000,
    queryFn: async () => unwrap(await api.GET('/api/v1/signature')) ?? null,
  })

/** Every change returns the new state; letters embed it, so they are refreshed too. */
function useChange<V>(fn: (v: V) => Promise<unknown>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export const useUploadSignature = () =>
  useChange(async (file: Blob) =>
    unwrap(
      await api.PUT('/api/v1/signature', {
        // Multipart `file` is typed `string` in the OpenAPI: see lib/api/documents.ts.
        body: { file: file as unknown as string },
        bodySerializer: (b) => {
          const form = new FormData()
          form.set('file', b.file as unknown as Blob)
          return form
        },
      }),
    ),
  )

export const useRotateSignature = () =>
  useChange(async (degrees: number) =>
    unwrap(await api.POST('/api/v1/signature/rotate', { body: { degrees } })),
  )

export const useDeleteSignature = () =>
  useChange(async () => void unwrap(await api.DELETE('/api/v1/signature')))

/** `null` takes the image off this letter. The response is the whole letter. */
export function useSetLetterSignature(letterId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (width_mm: number | null) =>
      unwrap(
        await api.PATCH('/api/v1/letters/{letter_id}/signature', {
          params: { path: { letter_id: letterId } },
          body: { width_mm },
        }),
      ),
    onSuccess: (l) => qc.setQueryData(['letter', letterId], l),
  })
}
