import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { unwrap } from '@/lib/api/unwrap'
import { useInvalidating } from '@/lib/query'
import type { Graph, Specs, VersionSpec } from './graph'

type S = components['schemas']
export type Agent = S['AgentOut']
export type AgentDetail = S['AgentDetail']
export type Flow = S['FlowOut']
export type FlowDetail = S['FlowDetail']
export type Run = S['RunOut']
export type RunSummary = S['RunSummary']
export type Step = S['StepOut']
export type RunListItem = S['RunListItem']
export type Schedule = S['ScheduleOut']
export type ScheduleIn = S['ScheduleIn']
export type Handoff = S['HandoffOut']
export type Avatar = S['Avatar']

const AGENTS = ['helpers']
const FLOWS = ['helper-flows']
const RUNS = ['helper-runs']
const SCHEDULES = ['helper-schedules']

export const useAgents = () =>
  useQuery({ queryKey: AGENTS, queryFn: async () => unwrap(await api.GET('/api/v1/agents')) })

export const useAgent = (id: string | undefined) =>
  useQuery({
    queryKey: [...AGENTS, id],
    enabled: !!id,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/agents/{agent_id}', { params: { path: { agent_id: id! } } })),
  })

/** The helper with its current version id: what a flow step pins when it is added. */
export function useFetchAgent() {
  const qc = useQueryClient()
  return (id: string) =>
    qc.fetchQuery({
      queryKey: [...AGENTS, id],
      staleTime: 0,
      queryFn: async () =>
        unwrap(await api.GET('/api/v1/agents/{agent_id}', { params: { path: { agent_id: id } } })),
    })
}

export const useAgentVersions = (id: string | undefined) =>
  useQuery({
    queryKey: [...AGENTS, id, 'versions'],
    enabled: !!id,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/agents/{agent_id}/versions', {
          params: { path: { agent_id: id! } },
        }),
      ),
  })

export const useCreateAgent = () =>
  useInvalidating(
    async (body: S['AgentCreate']) => unwrap(await api.POST('/api/v1/agents', { body })),
    [AGENTS],
  )

export const usePatchAgent = () =>
  useInvalidating(
    async (v: { id: string; body: S['AgentPatch'] }) =>
      unwrap(
        await api.PATCH('/api/v1/agents/{agent_id}', {
          params: { path: { agent_id: v.id } },
          body: v.body,
        }),
      ),
    [AGENTS],
  )

export const useArchiveAgent = () =>
  useInvalidating(
    async (id: string) =>
      void unwrap(
        await api.DELETE('/api/v1/agents/{agent_id}', { params: { path: { agent_id: id } } }),
      ),
    [AGENTS, FLOWS],
  )

/** Saves a new immutable version. `basedOn` is the version the editor started from: a stale
 *  editor gets a 409 instead of overwriting someone else's save. */
export const useAddVersion = () =>
  useInvalidating(
    async (v: { id: string; basedOn: number; spec: VersionSpec; note?: string }) =>
      unwrap(
        await api.POST('/api/v1/agents/{agent_id}/versions', {
          params: { path: { agent_id: v.id } },
          body: { based_on: v.basedOn, spec: v.spec, note: v.note ?? '' },
        }),
      ),
    [AGENTS],
  )

export const useTrial = () =>
  useMutation({
    mutationFn: async (v: {
      id: string
      spec: VersionSpec
      inputs: Record<string, string>
      jobId?: string | null
    }) =>
      unwrap(
        await api.POST('/api/v1/agents/{agent_id}/trial', {
          params: { path: { agent_id: v.id } },
          body: { spec: v.spec, inputs: v.inputs, job_id: v.jobId ?? null },
        }),
      ),
  })

// flows

export const useFlows = () =>
  useQuery({ queryKey: FLOWS, queryFn: async () => unwrap(await api.GET('/api/v1/flows')) })

export const useFlow = (id: string | undefined) =>
  useQuery({
    queryKey: [...FLOWS, id],
    enabled: !!id,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/flows/{flow_id}', { params: { path: { flow_id: id! } } })),
  })

export const useFlowVersions = (id: string | undefined) =>
  useQuery({
    queryKey: [...FLOWS, id, 'versions'],
    enabled: !!id,
    staleTime: 60_000,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/flows/{flow_id}/versions', { params: { path: { flow_id: id! } } }),
      ),
  })

/** The flow as the server has it now (a stale save is retried on top of this, never on a guess). */
export function useFetchFlow() {
  const qc = useQueryClient()
  return (id: string) =>
    qc.fetchQuery({
      queryKey: [...FLOWS, id],
      staleTime: 0,
      queryFn: async () =>
        unwrap(await api.GET('/api/v1/flows/{flow_id}', { params: { path: { flow_id: id } } })),
    })
}

export const useCreateFlow = () =>
  useInvalidating(
    async (body: S['FlowCreate']) => unwrap(await api.POST('/api/v1/flows', { body })),
    [FLOWS],
  )

export const useAddFlowVersion = () =>
  useInvalidating(
    async (v: { id: string; basedOn: number; graph: Graph; note?: string }) =>
      unwrap(
        await api.POST('/api/v1/flows/{flow_id}/versions', {
          params: { path: { flow_id: v.id } },
          body: { based_on: v.basedOn, graph: v.graph, note: v.note ?? '' },
        }),
      ),
    [FLOWS],
  )

export const usePatchFlow = () =>
  useInvalidating(
    async (v: { id: string; body: S['FlowPatch'] }) =>
      unwrap(
        await api.PATCH('/api/v1/flows/{flow_id}', {
          params: { path: { flow_id: v.id } },
          body: v.body,
        }),
      ),
    [FLOWS],
  )

export const useArchiveFlow = () =>
  useInvalidating(
    async (id: string) =>
      void unwrap(
        await api.DELETE('/api/v1/flows/{flow_id}', { params: { path: { flow_id: id } } }),
      ),
    [FLOWS],
  )

/** Server-side check of a draft graph (the validation panel). The server is the only judge. */
export const useValidate = () =>
  useMutation({
    mutationFn: async (graph: Graph) =>
      unwrap(await api.POST('/api/v1/flows/validate', { body: { graph } })),
  })

export const usePreview = () =>
  useMutation({
    mutationFn: async (v: { map: S['MapEntry'][]; outputs: Record<string, unknown> }) =>
      unwrap(await api.POST('/api/v1/flows/preview-handoff', { body: v })),
  })

export const useFlowRuns = (id: string | undefined) =>
  useQuery({
    queryKey: [...FLOWS, id, 'runs'],
    enabled: !!id,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/flows/{flow_id}/runs', { params: { path: { flow_id: id! } } })),
  })

export const useStartRun = () =>
  useInvalidating(
    async (v: { id: string; inputs: Record<string, string>; jobId?: string | null; key: string }) =>
      unwrap(
        await api.POST('/api/v1/flows/{flow_id}/runs', {
          params: { path: { flow_id: v.id }, header: { 'idempotency-key': v.key } },
          body: { inputs: v.inputs, job_id: v.jobId ?? null },
        }),
      ),
    [FLOWS],
  )

/** A run that has not ended yet (the pages keep following it). */
export const isLive = (status: RunSummary['status']) => status === 'queued' || status === 'running'

/** The run page follows a live run, then stops. */
export const useRun = (id: string | undefined) =>
  useQuery({
    queryKey: ['helper-run', id],
    enabled: !!id,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/flow-runs/{run_id}', { params: { path: { run_id: id! } } })),
    // While a run is live, look every 1.5 s; once it has ended, stop.
    refetchInterval: (q) => {
      const status = q.state.data?.status
      return status && isLive(status) ? 1_500 : false
    },
  })

export const useResumeRun = () =>
  useInvalidating(
    async (id: string) =>
      unwrap(
        await api.POST('/api/v1/flow-runs/{run_id}/resume', { params: { path: { run_id: id } } }),
      ),
    [['helper-run'], FLOWS, RUNS],
  )

export const useCancelRun = () =>
  useInvalidating(
    async (id: string) =>
      unwrap(
        await api.POST('/api/v1/flow-runs/{run_id}/cancel', { params: { path: { run_id: id } } }),
      ),
    [['helper-run'], FLOWS, RUNS],
  )

/** The specs of the helper versions a graph pins, for port names (inputs/outputs of a step).
 *  `ready` is false while a newly added helper's spec is still loading: linking waits for it. */
export function useSpecs(graph: Graph | undefined): { specs: Specs; ready: boolean } {
  const agents = [
    ...new Set((graph?.nodes ?? []).flatMap((n) => (n.type === 'agent' ? [n.agent_id] : []))),
  ]
  const qc = useQueryClient()
  const results = useQuery({
    queryKey: ['helper-specs', agents.sort().join(',')],
    enabled: agents.length > 0,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const map = new Map<string, VersionSpec>()
      for (const id of agents) {
        const versions = await qc.fetchQuery({
          queryKey: [...AGENTS, id, 'versions'],
          staleTime: 60_000,
          queryFn: async () =>
            unwrap(
              await api.GET('/api/v1/agents/{agent_id}/versions', {
                params: { path: { agent_id: id } },
              }),
            ),
        })
        for (const v of versions) map.set(v.id, v.spec)
      }
      return map
    },
  })
  const specs: Specs = results.data ?? new Map()
  const ready = (graph?.nodes ?? []).every(
    (n) => n.type !== 'agent' || specs.has(n.agent_version_id),
  )
  return { specs, ready }
}

/** A stale save: the server answered 409 (problem+json carries both `status` and `code`). */
export const isConflict = (e: unknown) => {
  const p = e as { status?: number; code?: string } | undefined
  return p?.status === 409 || p?.code === 'conflict'
}

const PAGE = 30

/** Every run of the account, newest first, filtered; "load more" pages by the last id. Refreshed
 *  every 10 s while one of the visible runs is still live. */
export const useAllRuns = (filter: { status?: RunSummary['status']; flowId?: string }) =>
  useInfiniteQuery({
    queryKey: [...RUNS, filter],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET('/api/v1/flow-runs', {
          params: {
            query: {
              status: filter.status,
              flow_id: filter.flowId,
              before_id: pageParam,
              limit: PAGE,
            },
          },
        }),
      ),
    getNextPageParam: (last) => (last.length === PAGE ? last[last.length - 1].id : undefined),
    refetchInterval: (q) =>
      q.state.data?.pages.some((p) => p.some((r) => isLive(r.status))) ? 10_000 : false,
  })

/** "Run again": a new run with the same inputs; the caller opens it. */
export const useRerun = () =>
  useInvalidating(
    async (id: string) =>
      unwrap(
        await api.POST('/api/v1/flow-runs/{run_id}/rerun', { params: { path: { run_id: id } } }),
      ),
    [FLOWS, RUNS],
  )

export const useSchedules = (flowId: string | undefined) =>
  useQuery({
    queryKey: [...SCHEDULES, flowId],
    enabled: !!flowId,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/flows/{flow_id}/schedules', {
          params: { path: { flow_id: flowId! } },
        }),
      ),
  })

export const useCreateSchedule = () =>
  useInvalidating(
    async (v: { flowId: string; body: ScheduleIn }) =>
      unwrap(
        await api.POST('/api/v1/flows/{flow_id}/schedules', {
          params: { path: { flow_id: v.flowId } },
          body: v.body,
        }),
      ),
    [SCHEDULES],
  )

export const useSetScheduleEnabled = () =>
  useInvalidating(
    async (v: { id: string; enabled: boolean }) =>
      unwrap(
        await api.PATCH('/api/v1/schedules/{schedule_id}', {
          params: { path: { schedule_id: v.id } },
          body: { enabled: v.enabled },
        }),
      ),
    [SCHEDULES],
  )

export const useDeleteSchedule = () =>
  useInvalidating(
    async (id: string) =>
      void unwrap(
        await api.DELETE('/api/v1/schedules/{schedule_id}', {
          params: { path: { schedule_id: id } },
        }),
      ),
    [SCHEDULES],
  )
