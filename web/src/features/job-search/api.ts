import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import { uploadDocument } from '@/lib/api/documents'
import type { components } from '@/lib/api/schema'
import { unwrap } from '@/lib/api/unwrap'

export type SearchParams = { query?: string; department?: string; contract_type?: string }
type JobIn =
  | components['schemas']['ManualJobIn']
  | components['schemas']['FileJobIn']
  | components['schemas']['SearchJobIn']

const KEY = ['jobs']

export const useJobs = () =>
  useQuery({ queryKey: KEY, queryFn: async () => unwrap(await api.GET('/api/v1/jobs')) })

const post = async (body: JobIn) => unwrap(await api.POST('/api/v1/jobs', { body }))

/** One mutation for the three entry paths; a File is uploaded as a `jd` document first. */
export function useAddJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: { text: string } | { file: File } | { externalId: string }) => {
      if ('text' in input) return post({ source: 'manual', text: input.text })
      if ('externalId' in input) {
        return post({ source: 'france_travail', external_id: input.externalId })
      }
      return post({ source: 'file', document_id: await uploadDocument('jd', input.file) })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

/** Runs only once the user submitted the search form (`params` set). */
export const useSearchJobs = (params: SearchParams | undefined) =>
  useQuery({
    queryKey: ['job-search', params],
    enabled: !!params,
    retry: false, // an upstream 503 should show at once, not after 3 retries
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const query = Object.fromEntries(Object.entries(params!).filter(([, v]) => v))
      return unwrap(await api.GET('/api/v1/jobs/search', { params: { query } }))
    },
  })
