import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { unwrap } from '@/lib/api/unwrap'

export type Fit = components['schemas']['FitAnalysisOut']
export type CompanyType = components['schemas']['FitAnalysisIn']['company_type']

export const useJob = (jobId: string) =>
  useQuery({
    queryKey: ['jobs', jobId],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/jobs/{job_id}', { params: { path: { job_id: jobId } } })),
  })

/** Latest stored analysis for the job, or `null` if none. */
export const useLatestFit = (jobId: string) =>
  useQuery({
    queryKey: ['fit', jobId],
    queryFn: async () => {
      const list = unwrap(
        await api.GET('/api/v1/fit-analyses', { params: { query: { job_id: jobId, limit: 1 } } }),
      )
      return list[0] ?? null
    },
  })

export function useRunFit(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (company_type: CompanyType) =>
      unwrap(await api.POST('/api/v1/fit-analyses', { body: { job_id: jobId, company_type } })),
    onSuccess: (fit) => qc.setQueryData(['fit', jobId], fit),
  })
}
