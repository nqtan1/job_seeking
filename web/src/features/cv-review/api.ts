import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { api } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { useTask } from '@/lib/api/tasks'
import { unwrap } from '@/lib/api/unwrap'

type S = components['schemas']
export type Review = S['CvReviewOut']
export type Block = S['Block']
export type Comment = S['BlockComment']
export type Criterion = Comment['criterion']
export type Quote = S['Quote']
type CvIn = S['CvReviewIn']
export type Track = CvIn['track']
export type Level = CvIn['level']
export const TRACKS: Track[] = [
  'backend',
  'frontend',
  'fullstack',
  'data',
  'devops',
  'ml',
  'mobile',
]
export const LEVELS: Level[] = ['intern', 'junior', 'mid', 'senior', 'staff']

const THI = {
  source: 'Tech Interview Handbook',
  url: 'https://www.techinterviewhandbook.org/resume/',
}
const XYZ = {
  source: 'Google XYZ formula',
  url: 'https://www.inc.com/bill-murphy-jr/google-recruiters-say-these-5-resume-tips-including-x-y-z-formula-will-improve-your-odds-of-getting-hired-at-google.html',
}
const IW = {
  source: 'InfoWorld',
  url: 'https://www.infoworld.com/article/3141949/10-resume-dos-and-donts-for-developers.html',
}
const SOURCE: Partial<Record<string, typeof THI>> = { impact: XYZ, scope: IW, progression: IW }

/** A rubric point's dimension (key of review.data.dimensions, its id prefix) and where it comes from. */
export const criterion = (id: Criterion) => {
  const dim = id.startsWith('skills') ? 'skills_ats' : id.split('.')[0]
  return { dim, ...(SOURCE[dim] ?? THI) }
}

export const useReviews = (enabled = true) =>
  useQuery({
    queryKey: ['cv-reviews'],
    enabled,
    queryFn: async () => unwrap(await api.GET('/api/v1/cv-reviews')),
  })

export const useReview = (id: string | null | undefined) =>
  useQuery({
    queryKey: ['cv-reviews', id],
    enabled: !!id,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/cv-reviews/{review_id}', { params: { path: { review_id: id! } } }),
      ),
  })

export type PdfLayout = S['PdfLayoutOut']

/** Where each block sits in the original PDF (404 for a DOCX/text CV: the page then stays text-only). */
export const usePdfLayout = (id: string) =>
  useQuery({
    queryKey: ['cv-pdf', id],
    retry: false,
    staleTime: Infinity,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/cv-reviews/{review_id}/layout', {
          params: { path: { review_id: id } },
        }),
      ),
  })

/** One page of the original PDF as a data URL (an <img src> cannot send the auth headers). */
export const usePdfPage = (id: string, page: number) =>
  useQuery({
    queryKey: ['cv-pdf', id, page],
    retry: false,
    staleTime: Infinity,
    queryFn: async () => {
      const blob = unwrap(
        await api.GET('/api/v1/cv-reviews/{review_id}/pages/{page}', {
          params: { path: { review_id: id, page } },
          parseAs: 'blob',
        }),
      ) as unknown as Blob
      return new Promise<string>((done) => {
        const r = new FileReader()
        r.onload = () => done(r.result as string)
        r.readAsDataURL(blob)
      })
    },
  })

export const useCvDocuments = () =>
  useQuery({
    queryKey: ['documents', 'cv'],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/documents', { params: { query: { kind: ['cv'] } } })),
  })

export function useDeleteReview() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) =>
      void unwrap(
        await api.DELETE('/api/v1/cv-reviews/{review_id}', { params: { path: { review_id: id } } }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cv-reviews'] }),
  })
}

const STALL_MS = 10 * 60_000 // two model calls of 240 s (one retry on a bad answer) + margin

/** Starts a review (from a document, or from edited blocks of a parent), polls its task and opens the result. */
export function useReviewRun() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const start = useMutation({
    mutationFn: async (body: CvIn) => unwrap(await api.POST('/api/v1/cv-reviews', { body })),
  })
  const poll = useTask(start.data?.task_id, 1000)
  const task = poll.data
  useEffect(() => {
    if (task?.status !== 'done' || !task.result_ref) return
    void qc.invalidateQueries({ queryKey: ['cv-reviews'] })
    navigate(`/cv-review/${task.result_ref}`)
  }, [task, qc, navigate])
  // The worker may have died: stop waiting after STALL_MS instead of polling for ever.
  const [stalledId, setStalledId] = useState<string>()
  const taskId = start.data?.task_id
  useEffect(() => {
    if (!taskId) return
    const t = setTimeout(() => setStalledId(taskId), STALL_MS)
    return () => clearTimeout(t)
  }, [taskId])
  const stalled = !!taskId && stalledId === taskId
  const failed = task?.status === 'failed' || (stalled && task?.status !== 'done')
  return {
    run: start.mutate,
    running: start.isPending || (start.isSuccess && !failed && !poll.isError),
    error:
      start.error ??
      poll.error ??
      (failed ? { code: task?.error_code ?? 'cv_review_failed' } : null),
  }
}

/** Rules-only live check: sync, no AI quota. */
export const useRecheck = () =>
  useMutation({
    mutationFn: async (body: S['RecheckIn']) =>
      unwrap(await api.POST('/api/v1/cv-reviews/recheck', { body })),
  })

export type Pin = { b: string; q: string }
/** Shared review state: what the evidence pieces read, so they take no plumbing props. */
type View = {
  texts: Record<string, string>
  original: Record<string, string>
  setText: (id: string, text: string) => void
  lineOf: (id: string) => number
  sel: string | null
  pin: Pin | null
  cites: Quote[]
  select: (id: string, pin?: Pin | null, toCv?: boolean) => void
}
export const ViewCtx = createContext<View>(null!)
