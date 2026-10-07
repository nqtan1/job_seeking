import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import { unwrap } from '@/lib/api/unwrap'

export const useMe = () =>
  useQuery({ queryKey: ['me'], queryFn: async () => unwrap(await api.GET('/api/v1/me')) })

/** Starts the export task; its id is polled with `useTask`. */
export const useStartExport = () =>
  useMutation({ mutationFn: async () => unwrap(await api.POST('/api/v1/me/export')) })

export const useDeleteAccount = () =>
  useMutation({ mutationFn: async () => void unwrap(await api.DELETE('/api/v1/me')) })

export function useSetReminders() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (email_reminders: boolean) =>
      void unwrap(await api.PATCH('/api/v1/me/preferences', { body: { email_reminders } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['me'] }),
  })
}
