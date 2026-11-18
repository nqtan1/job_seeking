import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { setLang, type Lang } from '@/i18n'
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

/** Switches the interface at once, then saves it to the account (AI answers and e-mails follow). */
export function useSetLanguage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (language: Lang) => {
      setLang(language)
      void unwrap(await api.PATCH('/api/v1/me/preferences', { body: { language } }))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['me'] }),
  })
}

/** Saved Jobs filters live on the account, so they follow the user to every device. */
export function useSetJobViews() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (job_views: Record<string, string>[]) =>
      void unwrap(await api.PATCH('/api/v1/me/preferences', { body: { job_views } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['me'] }),
  })
}

/** What the assistant remembers about the user (Settings › Memory). */
export const useMemory = () =>
  useQuery({
    queryKey: ['memory'],
    queryFn: async () => unwrap(await api.GET('/api/v1/profile/memory')),
  })

/** The server keeps the full list: every change sends all of it back (PUT replaces). */
export function useSaveMemory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (facts: components['schemas']['FactIn'][]) =>
      unwrap(await api.PUT('/api/v1/profile/memory', { body: { facts } })),
    onSuccess: (data) => qc.setQueryData(['memory'], data),
  })
}
