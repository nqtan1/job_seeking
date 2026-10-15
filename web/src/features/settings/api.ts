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

export const useAiCalls = () =>
  useQuery({
    queryKey: ['ai-calls'],
    queryFn: async () => unwrap(await api.GET('/api/v1/me/ai-calls')),
  })

export function useSetReminders() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (email_reminders: boolean) =>
      void unwrap(await api.PATCH('/api/v1/me/preferences', { body: { email_reminders } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['me'] }),
  })
}

export function useSetWeeklyGoal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (weekly_goal: number | null) =>
      void unwrap(await api.PATCH('/api/v1/me/preferences', { body: { weekly_goal } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['me'] }),
  })
}

/** "Sign out of all devices": needs a recent sign-in (the caller runs `ensureRecentAuth`). */
export const useRevokeSessions = () =>
  useMutation({ mutationFn: async () => void unwrap(await api.POST('/api/v1/me/sessions/revoke')) })
