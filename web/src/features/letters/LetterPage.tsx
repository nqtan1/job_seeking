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
import { useEditBlock, useLetter, usePdfPreview, useRender, useSpellcheck } from './api'
import { BlockEditor } from './BlockEditor'
import { editorBlocks, ideasFor } from './blocks'
import { ExportButtons, QualityPanel, VersionsPanel } from './panels'
import { activeIssues, applyAll, applyIssue, isStale, type Checked } from './spellcheck'

export function LetterPage() {
  const { letterId = '' } = useParams()
  // Keyed by id: drafts and spelling results never leak from one letter to the next.
  return <LetterEditor key={letterId} letterId={letterId} />
}

function LetterEditor({ letterId }: { letterId: string }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const letter = useLetter(letterId)
  const edit = useEditBlock(letterId)
  const render = useRender(letterId)
  const task = useTask(render.data?.task_id, 500) // renders take ~2 s: poll fast
  const pdf = usePdfPreview(letterId, letter.data?.pdf_document_id ?? null)
  // Unsaved edits only; everything else is read from the server copy.
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  // Spelling results, each tied to the text it was computed for (see `activeIssues`).
  const [checked, setChecked] = useState<Record<string, Checked>>({})
  const spell = useSpellcheck(letterId)

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

  // A letter the user writes themself starts with empty paragraphs: no PDF until they are done.
  const incomplete = editorBlocks(letter.data.content).some(
    (b) => b.block !== 'subject' && !b.text.trim(),
  )
  const blocks = editorBlocks(letter.data.content)
  type Block = (typeof blocks)[number]
  const textOf = (b: Block) => drafts[b.key] ?? b.text
  const issuesOf = (b: Block) => activeIssues(checked[b.key], textOf(b))
  const checkable = blocks.filter((b) => textOf(b).trim())
  // One call checks several paragraphs (the whole letter) or just one. A result is stored with
  // the text it was computed for: if the user typed meanwhile it shows as "edited since the
  // last check" rather than vanishing.
  const check = (keys: string[]) => {
    const items = checkable
      .filter((b) => keys.includes(b.key))
      .map((b) => ({ key: b.key, text: textOf(b) }))
    if (items.length === 0) return
    spell.mutate(items, {
      onSuccess: (r) =>
        setChecked((prev) => ({
          ...prev,
          ...Object.fromEntries(
            items.map((it) => [
              it.key,
              { text: it.text, issues: r.issues.filter((i) => i.key === it.key), ignored: 0 },
            ]),
          ),
        })),
    })
  }
  const keep = (b: Block, text: string, issues: Checked['issues'], ignored = 0) =>
    setChecked((prev) => ({
      ...prev,
      [b.key]: { text, issues, ignored: (prev[b.key]?.ignored ?? 0) + ignored },
    }))
  const accept = (b: Block, text: string, issues: Checked['issues']) => {
    setDrafts((d) => ({ ...d, [b.key]: text }))
    keep(b, text, issues)
  }
  const checking = spell.isPending ? (spell.variables ?? []).map((v) => v.key) : []
  const errorKeys = spell.isError ? (spell.variables ?? []).map((v) => v.key) : []
  const allIssues = blocks.flatMap((b) => issuesOf(b) ?? [])
  const checkedCount = checkable.filter((b) => issuesOf(b) !== undefined).length
  const corrections = `${allIssues.length} ${allIssues.length === 1 ? 'correction' : 'corrections'}`
  const unsaved = blocks.filter((b) => drafts[b.key] !== undefined && drafts[b.key] !== b.text)
  // Several paragraphs corrected at once would otherwise need one Save each.
  const saveAll = async () => {
    for (const b of unsaved) {
      const text = drafts[b.key]
      if (!text.trim()) continue
      try {
        await edit.mutateAsync({ block: b.block, index: b.index, text })
      } catch {
        return // the error is shown below; the remaining drafts stay
      }
      setDrafts(({ [b.key]: _saved, ...rest }) => rest)
    }
  }
  const rendering = render.isPending || status === 'queued'
  const renderFailed = status === 'failed' || render.isError

  return (
    <Page
      title={letter.data.content.subject || 'Cover letter'}
      description={
        letter.data.ideas
          ? 'Write each paragraph in your own words, using the ideas, then render the PDF.'
          : 'Edit a paragraph, then render the PDF to preview it.'
      }
      back={back}
      wide
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            disabled={rendering || incomplete}
            title={incomplete ? 'Write and save every paragraph first' : undefined}
            onClick={() => render.mutate()}
          >
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
          <div className="flex flex-wrap items-center gap-3">
            <Button
              size="sm"
              variant="outline"
              disabled={spell.isPending || checkable.length === 0}
              aria-busy={spell.isPending && checking.length > 1}
              onClick={() => check(blocks.map((b) => b.key))}
            >
              {spell.isPending && checking.length > 1
                ? 'Checking spelling…'
                : 'Check spelling of the whole letter'}
            </Button>
            {allIssues.length > 1 && (
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  blocks.forEach((b) => {
                    const issues = issuesOf(b)
                    if (issues?.length) accept(b, applyAll(textOf(b), issues), [])
                  })
                }
              >
                Apply all {allIssues.length} corrections
              </Button>
            )}
            {unsaved.length > 1 && (
              <Button size="sm" disabled={edit.isPending} onClick={saveAll}>
                {edit.isPending ? 'Saving…' : `Save ${unsaved.length} changes`}
              </Button>
            )}
            <span role="status" aria-live="polite" className="text-sm text-muted-foreground">
              {checkedCount === 0
                ? ''
                : checkedCount < checkable.length
                  ? `Checked ${checkedCount} of ${checkable.length} paragraphs: ${
                      allIssues.length === 0 ? 'no issue so far' : `${corrections} suggested`
                    }.`
                  : allIssues.length === 0
                    ? 'No spelling or grammar issue found.'
                    : `${corrections} suggested below.`}
            </span>
          </div>
          {spell.isError && errorKeys.length > 1 && <ErrorMessage error={spell.error} />}
          {blocks.map((b) => (
            <BlockEditor
              key={b.key}
              letterId={letterId}
              block={b}
              value={drafts[b.key] ?? b.text}
              ideas={ideasFor(letter.data.ideas, b)}
              issues={issuesOf(b)}
              ignored={checked[b.key]?.ignored}
              staleCheck={isStale(checked[b.key], textOf(b))}
              checking={checking.includes(b.key)}
              checkDisabled={spell.isPending}
              checkError={
                errorKeys.length === 1 && errorKeys[0] === b.key ? spell.error : undefined
              }
              onCheck={() => check([b.key])}
              onApplyIssue={(i) => {
                const r = applyIssue(textOf(b), issuesOf(b) ?? [], i)
                accept(b, r.text, r.issues)
              }}
              onApplyAll={() => accept(b, applyAll(textOf(b), issuesOf(b) ?? []), [])}
              onIgnoreIssue={(i) =>
                keep(
                  b,
                  textOf(b),
                  (issuesOf(b) ?? []).filter((_, n) => n !== i),
                  1,
                )
              }
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
