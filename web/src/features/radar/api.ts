import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { unwrap } from '@/lib/api/unwrap'

export type Search = components['schemas']['RadarSearchOut']
export type SearchIn = components['schemas']['RadarSearchIn']
export type Result = components['schemas']['RadarResultOut']

const SEARCHES = ['radar-searches']
const RESULTS = ['radar-results']
const RUNS = ['radar-runs']
const STATUS = ['radar-status']
const INSIGHTS = ['radar-insights']

export const useSearches = () =>
  useQuery({
    queryKey: SEARCHES,
    queryFn: async () => unwrap(await api.GET('/api/v1/radar/searches')),
  })

export type ResultStatus = 'new' | 'approved' | 'dismissed' | 'skipped'

export const useResults = (status: ResultStatus = 'new', enabled = true) =>
  useQuery({
    queryKey: [...RESULTS, status],
    enabled,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/radar/results', { params: { query: { status } } })),
  })

/** New matches, working or idle, last and next run: polled faster while a run is going on. */
let pollFastUntil = 0
/** After "Run now" the strip checks often for a short while: the run is queued, not started yet. */
const pollRadarFast = () => {
  pollFastUntil = Date.now() + 20_000
}

/**
 * The radar at a glance. Everywhere (the menu badge) it is checked once a minute. Only the radar
 * page asks for closer following (`follow`): every 5 s while a run goes on, every 3 s in the 20 s
 * after a run was requested. Browsers stop polling hidden tabs by themselves.
 */
export const useRadarStatus = (follow = false) =>
  useQuery({
    queryKey: STATUS,
    queryFn: async () => unwrap(await api.GET('/api/v1/radar/status')),
    refetchInterval: (q) => {
      if (!follow) return 60_000
      if (q.state.data?.running) return 5_000
      return Date.now() < pollFastUntil ? 3_000 : 60_000
    },
  })

export const useInsights = () =>
  useQuery({
    queryKey: INSIGHTS,
    queryFn: async () => unwrap(await api.GET('/api/v1/radar/insights')),
  })

/** The user opened their matches: the menu badge goes back to zero. */
export const useMarkSeen = () =>
  useInvalidating(async () => void unwrap(await api.POST('/api/v1/radar/results/seen')), [STATUS])

/** "Review anyway": a job the radar rejected goes into the user's jobs (no AI call). */
export const useKeepAnyway = () =>
  useInvalidating(
    async (id: string) =>
      unwrap(
        await api.POST('/api/v1/radar/results/{result_id}/keep', {
          params: { path: { result_id: id } },
        }),
      ),
    [RESULTS, STATUS, INSIGHTS, ['jobs']],
  )

export const useAiUse = () =>
  useQuery({
    queryKey: ['radar-usage'],
    queryFn: async () => unwrap(await api.GET('/api/v1/radar/usage')),
  })

export const useRuns = () =>
  useQuery({
    queryKey: RUNS,
    queryFn: async () => unwrap(await api.GET('/api/v1/radar/runs')),
  })

function useInvalidating<V, R>(fn: (v: V) => Promise<R>, keys: string[][]) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => keys.forEach((queryKey) => qc.invalidateQueries({ queryKey })),
  })
}

export const useCreateSearch = () =>
  useInvalidating(
    async (body: SearchIn) => unwrap(await api.POST('/api/v1/radar/searches', { body })),
    [SEARCHES, STATUS],
  )

export const useDeleteSearch = () =>
  useInvalidating(
    async (id: string) =>
      void unwrap(
        await api.DELETE('/api/v1/radar/searches/{search_id}', {
          params: { path: { search_id: id } },
        }),
      ),
    [SEARCHES, RESULTS, RUNS, STATUS, INSIGHTS],
  )

export type SearchUpdate = components['schemas']['RadarSearchUpdate']

export const useUpdateSearch = () =>
  useInvalidating(
    async (v: { id: string; changes: SearchUpdate }) =>
      unwrap(
        await api.PATCH('/api/v1/radar/searches/{search_id}', {
          params: { path: { search_id: v.id } },
          body: v.changes,
        }),
      ),
    [SEARCHES, STATUS],
  )

export const useToggleSearch = () =>
  useInvalidating(
    async (v: { id: string; enabled: boolean }) =>
      unwrap(
        await api.PATCH('/api/v1/radar/searches/{search_id}', {
          params: { path: { search_id: v.id } },
          body: { enabled: v.enabled },
        }),
      ),
    [SEARCHES, STATUS],
  )

/** Queues a run; the returned task id is polled with `useTask`. */
export const useRunSearch = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.POST('/api/v1/radar/searches/{search_id}/run', {
          params: { path: { search_id: id } },
        }),
      ),
    onSuccess: () => {
      pollRadarFast()
      qc.invalidateQueries({ queryKey: STATUS })
    },
  })
}

export const useDecide = () =>
  useInvalidating(
    async (v: { id: string; action: 'approve' | 'dismiss' }) =>
      void unwrap(
        await api.POST(
          v.action === 'approve'
            ? '/api/v1/radar/results/{result_id}/approve'
            : '/api/v1/radar/results/{result_id}/dismiss',
          { params: { path: { result_id: v.id } } },
        ),
      ),
    [RESULTS, STATUS, INSIGHTS, ['jobs'], ['fit-all']],
  )

export const REFRESH_AFTER_RUN = [
  SEARCHES,
  RESULTS,
  RUNS,
  STATUS,
  INSIGHTS,
  ['jobs'],
  ['radar-usage'],
]

/** Ids of the jobs the radar brought in (kept or approved), to tag them in the jobs list. */
export function useRadarJobIds(): Set<string> {
  const fresh = useResults('new')
  const kept = useResults('approved')
  return new Set(
    [...(fresh.data ?? []), ...(kept.data ?? [])].flatMap((r) => (r.job_id ? [r.job_id] : [])),
  )
}
