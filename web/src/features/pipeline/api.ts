import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import { unwrap } from '@/lib/api/unwrap'
import { useApplications } from '@/features/tracker/api'
import { useLetters } from '@/features/letters/api'

/** Every stored fit analysis, newest first (one request, so the job list can rank them). */
export const useAllFits = () =>
  useQuery({
    queryKey: ['fit-all'],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/fit-analyses', { params: { query: { limit: 100 } } })),
  })

/** For each job: its latest fit, its letters and its application, so the user can compare. */
export function usePipeline() {
  const fits = useAllFits()
  const letters = useLetters()
  const apps = useApplications()
  const latestFit = new Map<string, NonNullable<typeof fits.data>[number]>()
  for (const f of fits.data ?? []) if (!latestFit.has(f.job_id)) latestFit.set(f.job_id, f)
  return {
    fit: (jobId: string) => latestFit.get(jobId),
    letters: (jobId: string) => letters.data?.filter((l) => l.job_id === jobId) ?? [],
    application: (jobId: string) => apps.data?.find((a) => a.job_id === jobId),
  }
}

type ApplyArgs = {
  jobId: string
  source: 'france_travail' | 'other'
  status: 'to_apply' | 'applied'
  /** The letter's rendered PDF, attached so the user can re-read what they sent. */
  pdfDocumentId?: string | null
}

/** Put a job in the tracker (planned or already applied), attaching the letter PDF if any. */
export function useApply() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (v: ApplyArgs) => {
      const app = unwrap(
        await api.POST('/api/v1/applications', {
          body: { job_id: v.jobId, source: v.source, status: v.status },
        }),
      )
      if (v.pdfDocumentId)
        unwrap(
          await api.POST('/api/v1/applications/{application_id}/documents', {
            params: { path: { application_id: app.id } },
            body: { document_id: v.pdfDocumentId },
          }),
        )
      return app
    },
    onSuccess: () =>
      // the radar's story follows the tracker: its insights and each match's status change too
      ['applications', 'radar-insights', 'radar-results', 'radar-status'].forEach((key) =>
        qc.invalidateQueries({ queryKey: [key] }),
      ),
  })
}
