import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { FileText } from 'lucide-react'
import { useNavigate, useParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { StepProgress } from '@/components/StepProgress'
import { Button } from '@/components/ui/button'
import { ApplyActions } from '@/features/pipeline/ApplyActions'
import { useTask } from '@/lib/api/tasks'
import { describeError } from '@/lib/problem'
import { DeleteLetterButton } from './DeleteLetterButton'
import { useEditBlock, useLetter, usePdfPreview, useRender } from './api'
import { BlockEditor } from './BlockEditor'
import { editorBlocks } from './blocks'
import { ExportButtons, QualityPanel, VersionsPanel } from './panels'

export function LetterPage() {
  const { letterId = '' } = useParams()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const letter = useLetter(letterId)
  const edit = useEditBlock(letterId)
  const render = useRender(letterId)
  const task = useTask(render.data?.task_id, 500) // renders take ~2 s: poll fast
  const pdf = usePdfPreview(letterId, letter.data?.pdf_document_id ?? null)
  // Unsaved edits only; everything else is read from the server copy.
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  const status = task.data?.status
  useEffect(() => {
    if (status === 'done') qc.invalidateQueries({ queryKey: ['letter', letterId] })
  }, [status, qc, letterId])

  const back = { to: '/letters', label: 'Letters' }
  if (letter.isPending)
    return (
      <Page title="Cover letter" back={back}>
        <ListSkeleton />
      </Page>
    )
  if (letter.isError)
    return (
      <Page title="Cover letter" back={back}>
        <ErrorMessage error={letter.error} />
      </Page>
    )

  const rendering = render.isPending || status === 'queued'
  const renderFailed = status === 'failed' || render.isError

  return (
    <Page
      title={letter.data.content.subject || 'Cover letter'}
      description="Edit a paragraph, then render the PDF to preview it."
      back={back}
      wide
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={rendering} onClick={() => render.mutate()}>
            {rendering ? 'Rendering PDF…' : 'Render PDF'}
          </Button>
          <DeleteLetterButton id={letterId} onDeleted={() => navigate('/letters')} />
          {letter.data.job_id && (
            <ApplyActions jobId={letter.data.job_id} pdfDocumentId={letter.data.pdf_document_id} />
          )}
        </div>
      }
    >
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          {editorBlocks(letter.data.content).map((b) => (
            <BlockEditor
              key={b.key}
              letterId={letterId}
              block={b}
              value={drafts[b.key] ?? b.text}
              saving={edit.isPending}
              onChange={(text) => setDrafts({ ...drafts, [b.key]: text })}
              onSave={() =>
                edit.mutate(
                  { block: b.block, index: b.index, text: drafts[b.key] ?? b.text },
                  { onSuccess: () => setDrafts(({ [b.key]: _saved, ...rest }) => rest) },
                )
              }
            />
          ))}
          {edit.isError && <ErrorMessage error={edit.error} />}
        </div>

        <div className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <ExportButtons letterId={letterId} />
          {rendering && <StepProgress steps={['Typesetting your letter…']} />}
          {pdf.failed && (
            <p role="alert" className="text-sm text-destructive">
              The PDF preview could not be loaded. Try rendering again.
            </p>
          )}
          {renderFailed && (
            <p role="alert" className="text-sm text-destructive">
              {render.isError
                ? describeError(render.error)
                : 'The PDF could not be rendered. Please try again.'}
            </p>
          )}
          {pdf.url ? (
            <iframe
              title="Letter PDF preview"
              src={pdf.url}
              className="h-[70vh] w-full rounded-xl border bg-white shadow-xs"
            />
          ) : (
            <EmptyState
              icon={FileText}
              title="No preview yet"
              description="Render the PDF to preview your letter. Save your edits first."
            />
          )}
          <QualityPanel letterId={letterId} />
          <VersionsPanel letterId={letterId} onRestored={() => setDrafts({})} />
        </div>
      </div>
    </Page>
  )
}
