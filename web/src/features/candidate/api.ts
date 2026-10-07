import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import { uploadDocument } from '@/lib/api/documents'
import type { components } from '@/lib/api/schema'
import { unwrap } from '@/lib/api/unwrap'

export type Profile = components['schemas']['ProfileOut']
export type ProfilePatch = components['schemas']['ProfileUpdate']

const KEY = ['profile']

/** `null` = no profile yet (404): the onboarding state. */
export const useProfile = () =>
  useQuery({
    queryKey: KEY,
    queryFn: async () => {
      const result = await api.GET('/api/v1/profile')
      return result.response.status === 404 ? null : unwrap(result)
    },
  })

export function useExtractProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const document_id = await uploadDocument('cv', file)
      return unwrap(await api.POST('/api/v1/profile/extract', { body: { document_id } }))
    },
    onSuccess: (profile) => qc.setQueryData(KEY, profile),
  })
}

export function useUpdateProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: ProfilePatch) => unwrap(await api.PATCH('/api/v1/profile', { body })),
    onSuccess: (profile) => qc.setQueryData(KEY, profile),
  })
}
