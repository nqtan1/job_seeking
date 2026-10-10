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

/** Where to apply for a saved job, from the cached inbox list. http(s) only: the URL comes
 *  from a third-party provider. ponytail: the list is capped at 50 jobs, a per-job lookup if
 *  an inbox outgrows it. */
export function useApplyUrl(jobId: string | null | undefined): string | null {
  const url = useJobs().data?.find((j) => j.id === jobId)?.data.source_meta.apply_url
  return url && /^https?:\/\//i.test(url) ? url : null
}

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
