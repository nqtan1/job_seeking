import { useState } from 'react'
import { useI18n } from '@/i18n'
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

const KINDS = ['cv', 'letter_pdf', 'attachment']

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
  const { t, locale } = useI18n()
  const docName = (d: { kind: string; created_at: string; size: number }) =>
    `${KINDS.includes(d.kind) ? t(`tracker.docs.kind_${d.kind}` as 'tracker.docs.kind_cv') : d.kind} · ${new Date(d.created_at).toLocaleDateString(locale)} · ${Math.max(1, Math.round(d.size / 1024))} KB`
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
      label={t('tracker.docs.label', { name })}
      title={t('tracker.docs.title')}
      subtitle={name}
      side="left"
      onClose={onClose}
    >
      {attached.isPending && (
        <p className="text-xs text-muted-foreground">{t('tracker.docs.loading')}</p>
      )}
      {attached.isError && <ErrorMessage error={attached.error} />}
      {attached.data && docs.length === 0 && (
        <p className="text-sm text-muted-foreground">{t('tracker.docs.none')}</p>
      )}
      <div className="flex flex-wrap gap-2" role="tablist" aria-label={t('tracker.docs.attached')}>
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
              {t('tracker.docs.open')}
            </a>
            <a
              href={current.save_url}
              className="text-xs underline underline-offset-2"
              aria-label={t('tracker.docs.download_aria', { file: current.filename })}
            >
              {t('tracker.docs.download')}
            </a>
            <Button
              size="sm"
              variant="ghost"
              disabled={detach.isPending}
              aria-label={t('tracker.docs.remove_aria', { file: current.filename })}
              onClick={() =>
                detach.mutate(current.document_id, { onSuccess: () => setPicked(undefined) })
              }
            >
              {t('tracker.docs.remove')}
            </Button>
          </div>
        </>
      )}
      {choices.length > 0 && (
        <NativeSelect
          aria-label={t('tracker.docs.attach_aria')}
          className="w-full"
          value=""
          disabled={attach.isPending}
          onChange={(e) =>
            attach.mutate(e.target.value, { onSuccess: () => setPicked(e.target.value) })
          }
        >
          <NativeSelectOption value="" disabled>
            {t('tracker.docs.attach')}
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
