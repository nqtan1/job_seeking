import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import { unwrap } from '@/lib/api/unwrap'

/** Polls a background task until it is done or failed. */
export const useTask = (taskId: string | undefined, pollMs = 1500) =>
  useQuery({
    queryKey: ['task', taskId],
    enabled: !!taskId,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/tasks/{task_id}', { params: { path: { task_id: taskId! } } })),
    refetchInterval: (q) => (q.state.data?.status === 'queued' || !q.state.data ? pollMs : false),
  })
