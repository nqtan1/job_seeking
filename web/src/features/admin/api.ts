import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import { unwrap } from '@/lib/api/unwrap'

export const PAGE = 25

export const useAdminUsers = (q: string, page: number) =>
  useQuery({
    queryKey: ['admin-users', q, page],
    placeholderData: keepPreviousData,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/admin/users', {
          params: { query: { q: q || undefined, limit: PAGE, offset: page * PAGE } },
        }),
      ),
  })

export const useAdminStats = () =>
  useQuery({
    queryKey: ['admin-stats'],
    queryFn: async () => unwrap(await api.GET('/api/v1/admin/stats')),
  })

export function useSetBlocked() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (v: { id: string; blocked: boolean }) =>
      void unwrap(
        await api.POST(
          v.blocked
            ? '/api/v1/admin/users/{user_id}/block'
            : '/api/v1/admin/users/{user_id}/unblock',
          { params: { path: { user_id: v.id } } },
        ),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  })
}

export const useAiConsole = () =>
  useQuery({
    queryKey: ['admin-ai'],
    queryFn: async () => unwrap(await api.GET('/api/v1/admin/ai')),
  })

export function useSetAiModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (v: { feature: string; provider: string; model: string }) =>
      void unwrap(
        await api.PUT('/api/v1/admin/ai/{feature}', {
          params: { path: { feature: v.feature } },
          body: { provider: v.provider, model: v.model },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-ai'] }),
  })
}

export function useResetAiModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (feature: string) =>
      void unwrap(
        await api.DELETE('/api/v1/admin/ai/{feature}', { params: { path: { feature } } }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-ai'] }),
  })
}
