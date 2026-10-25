import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import { uploadDocument } from '@/lib/api/documents'
import type { components } from '@/lib/api/schema'
import { unwrap } from '@/lib/api/unwrap'
import { toast } from '@/lib/toast'
import { REFRESH_AFTER_RUN } from '@/features/radar/api'

export type SearchParams = { query?: string; department?: string; contract_type?: string }
type JobIn = components['schemas']['ManualJobIn'] | components['schemas']['SearchJobIn']

export type Job = components['schemas']['JobOut']
export type JobPatch = components['schemas']['JobPatch']

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

/** The API answers 201 for a new job and 200 when the same input was added before (nothing was
 *  analysed, the existing job comes back). */
const ALREADY_ADDED = 200
const DUPLICATE_MESSAGE = 'Already in your jobs: nothing new was analysed.'

const post = async (body: JobIn) => {
  const res = await api.POST('/api/v1/jobs', { body })
  return { job: unwrap(res), already: res.response.status === ALREADY_ADDED }
}

/** The manual and France Travail entry paths: one job each. */
export function useAddJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: { text: string } | { externalId: string }) =>
      'text' in input
        ? post({ source: 'manual', text: input.text })
        : post({ source: 'france_travail', external_id: input.externalId }),
    onSuccess: ({ job, already }) => {
      toast(already ? DUPLICATE_MESSAGE : `Job added: ${job.data.title}`)
      return qc.invalidateQueries({ queryKey: KEY })
    },
  })
}

export const MAX_FILES = 10 // keep in sync with MAX_FILES in backend jobs/schemas.py

/** Add job description files (PDF/Word/image/TXT) as ONE batch: the model reads them together, so
 *  pages of one offer merge and the cost is one pass, not one per file. All-or-nothing; the
 *  user retries the batch. ponytail: files uploaded before a failure stay as unused documents
 *  until the retention sweep. */
export function useAddJobFiles() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (files: File[]) => {
      const document_ids = await Promise.all(files.map((f) => uploadDocument('jd', f)))
      const res = await api.POST('/api/v1/jobs/from-file', {
        body: { source: 'file', document_ids },
      })
      return { jobs: unwrap(res), already: res.response.status === ALREADY_ADDED }
    },
    onSuccess: ({ jobs, already }) => {
      toast(already ? DUPLICATE_MESSAGE : `${jobs.length} job${jobs.length > 1 ? 's' : ''} added`)
      return qc.invalidateQueries({ queryKey: KEY })
    },
  })
}

/** A sentence -> filters. Nothing is searched: the user reviews them in the form first. */
export const useParseQuery = () =>
  useMutation({
    mutationFn: async (text: string) =>
      unwrap(await api.POST('/api/v1/jobs/query', { body: { text } })),
  })

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

/** Remove a job. What hangs off it changes too: its fit report goes, letters and tracked
 *  applications lose the link, and a radar match for it leaves the list. */
export function useDeleteJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) =>
      void unwrap(await api.DELETE('/api/v1/jobs/{job_id}', { params: { path: { job_id: id } } })),
    onSuccess: () =>
      Promise.all(
        [...REFRESH_AFTER_RUN, ['fit-all'], ['letters'], ['applications']].map((queryKey) =>
          qc.invalidateQueries({ queryKey }),
        ),
      ),
  })
}

/** Fill in what the model could not extract; a blank string clears a field. Refetch on success
 *  (the server's answer is the truth, nothing is applied optimistically). */
export function usePatchJob(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: JobPatch) =>
      unwrap(await api.PATCH('/api/v1/jobs/{job_id}', { params: { path: { job_id: id } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
