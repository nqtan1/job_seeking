import { api } from '@/lib/api/client'
import { unwrap } from '@/lib/api/unwrap'

/** Upload a CV or job description; returns the stored document's id. */
export async function uploadDocument(kind: 'cv' | 'jd', file: File): Promise<string> {
  const doc = unwrap(
    await api.POST('/api/v1/documents', {
      // The OpenAPI types the multipart `file` as `string` (no binary format), so cast it; the
      // serializer sends the real File as multipart.
      body: { kind, file: file as unknown as string },
      bodySerializer: (b) => {
        const form = new FormData()
        form.set('kind', b.kind)
        form.set('file', b.file as unknown as Blob)
        return form
      },
    }),
  )
  return doc.document_id
}
