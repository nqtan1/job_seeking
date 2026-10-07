import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import { unwrap } from '@/lib/api/unwrap'
import type { components } from '@/lib/api/schema'

export type Application = components['schemas']['ApplicationOut']
export type ApplicationIn = components['schemas']['ApplicationIn']
export type Status = Application['status']

const KEY = ['applications']

export const useApplications = () =>
  useQuery({ queryKey: KEY, queryFn: async () => unwrap(await api.GET('/api/v1/applications')) })

export const useEvents = (id: string, enabled: boolean) =>
  useQuery({
    queryKey: ['events', id],
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/applications/{application_id}/events', {
          params: { path: { application_id: id } },
        }),
      ),
  })

export function useCreateApplication() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: ApplicationIn) =>
      unwrap(await api.POST('/api/v1/applications', { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useChangeStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (v: { id: string; status: Status }) =>
      unwrap(
        await api.POST('/api/v1/applications/{application_id}/status', {
          params: { path: { application_id: v.id } },
          body: { status: v.status },
        }),
      ),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: KEY })
      qc.invalidateQueries({ queryKey: ['events', v.id] })
    },
  })
}

export function useDeleteApplication() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) =>
      void unwrap(
        await api.DELETE('/api/v1/applications/{application_id}', {
          params: { path: { application_id: id } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

const docsKey = (id: string) => ['application-documents', id]

export const useApplicationDocuments = (id: string, enabled: boolean) =>
  useQuery({
    queryKey: docsKey(id),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/applications/{application_id}/documents', {
          params: { path: { application_id: id } },
        }),
      ),
  })

/** The user's files that can be attached: CV, letter PDFs, other attachments. */
export const useAvailableDocuments = (enabled: boolean) =>
  useQuery({
    queryKey: ['documents'],
    enabled,
    queryFn: async () => unwrap(await api.GET('/api/v1/documents')),
  })

export function useAttachDocument(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (documentId: string) =>
      void unwrap(
        await api.POST('/api/v1/applications/{application_id}/documents', {
          params: { path: { application_id: id } },
          body: { document_id: documentId },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: docsKey(id) }),
  })
}

export function useDetachDocument(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (documentId: string) =>
      void unwrap(
        await api.DELETE('/api/v1/applications/{application_id}/documents/{document_id}', {
          params: { path: { application_id: id, document_id: documentId } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: docsKey(id) }),
  })
}

export type ApplicationUpdate = components['schemas']['ApplicationUpdate']

export function useUpdateApplication() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (v: { id: string; changes: ApplicationUpdate }) =>
      unwrap(
        await api.PATCH('/api/v1/applications/{application_id}', {
          params: { path: { application_id: v.id } },
          body: v.changes,
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
