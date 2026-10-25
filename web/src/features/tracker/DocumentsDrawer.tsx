import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import {
  useApplicationDocuments,
  useAttachDocument,
  useAvailableDocuments,
  useDetachDocument,
  type Application,
} from './api'
import { Drawer } from './Drawer'

const KIND_LABEL: Record<string, string> = {
  cv: 'CV',
  letter_pdf: 'Letter (PDF)',
  attachment: 'Attachment',
}
const docName = (d: { kind: string; created_at: string; size: number }) =>
  `${KIND_LABEL[d.kind] ?? d.kind} · ${new Date(d.created_at).toLocaleDateString()} · ${Math.max(1, Math.round(d.size / 1024))} KB`

/** Left-side reader: the files sent with this application, viewable in place (interview prep). */
export function DocumentsDrawer({
  app,
  name,
  onClose,
}: {
  app: Application
  name: string
  onClose: () => void
}) {
  const attached = useApplicationDocuments(app.id, true)
  const available = useAvailableDocuments(true)
  const attach = useAttachDocument(app.id)
  const detach = useDetachDocument(app.id)
  const [picked, setPicked] = useState<string>()
  const docs = attached.data ?? []
  const current = docs.find((d) => d.document_id === picked) ?? docs[0]
  const taken = new Set(docs.map((d) => d.document_id))
  const choices = (available.data ?? []).filter((d) => !taken.has(d.document_id))
  return (
    <Drawer
      label={`Documents for ${name}`}
      title="Documents sent"
      subtitle={name}
      side="left"
      onClose={onClose}
    >
      {attached.isPending && <p className="text-xs text-muted-foreground">Loading documents…</p>}
      {attached.isError && <ErrorMessage error={attached.error} />}
      {attached.data && docs.length === 0 && (
        <p className="text-sm text-muted-foreground">No documents attached yet.</p>
      )}
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Attached documents">
        {docs.map((d) => (
          <Button
            key={d.document_id}
            size="sm"
            role="tab"
            aria-selected={d.document_id === current?.document_id}
            variant={d.document_id === current?.document_id ? 'default' : 'outline'}
            onClick={() => setPicked(d.document_id)}
          >
            {d.filename}
          </Button>
        ))}
      </div>
      {current && (
        <>
          {current.mime.startsWith('image/') ? (
            <img
              src={current.download_url}
              alt={current.filename}
              className="min-h-64 flex-1 rounded-lg border bg-white object-contain"
            />
          ) : (
            <iframe
              title={current.filename}
              src={current.download_url}
              className="min-h-64 flex-1 rounded-lg border bg-white"
            />
          )}
          <div className="flex gap-2">
            <a
              href={current.download_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs underline underline-offset-2"
            >
              Open in new tab
            </a>
            <a
              href={current.save_url}
              className="text-xs underline underline-offset-2"
              aria-label={`Download ${current.filename}`}
            >
              Download
            </a>
            <Button
              size="sm"
              variant="ghost"
              disabled={detach.isPending}
              aria-label={`Remove ${current.filename}`}
              onClick={() =>
                detach.mutate(current.document_id, { onSuccess: () => setPicked(undefined) })
              }
            >
              Remove from this application
            </Button>
          </div>
        </>
      )}
      {choices.length > 0 && (
        <NativeSelect
          aria-label="Attach a document"
          className="w-full"
          value=""
          disabled={attach.isPending}
          onChange={(e) =>
            attach.mutate(e.target.value, { onSuccess: () => setPicked(e.target.value) })
          }
        >
          <NativeSelectOption value="" disabled>
            Attach a document…
          </NativeSelectOption>
          {choices.map((d) => (
            <NativeSelectOption key={d.document_id} value={d.document_id}>
              {docName(d)}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      )}
      {(attach.isError || detach.isError) && <ErrorMessage error={attach.error ?? detach.error} />}
    </Drawer>
  )
}
