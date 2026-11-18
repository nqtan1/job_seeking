import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'
import { FileText } from 'lucide-react'
import { useNavigate, useParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { StepProgress } from '@/components/StepProgress'
import { Button } from '@/components/ui/button'
import { ApplyActions } from '@/features/pipeline/ApplyActions'
import { useT } from '@/i18n'
import { useTask } from '@/lib/api/tasks'
import { describeError } from '@/lib/problem'
import { DeleteLetterButton } from './DeleteLetterButton'
import {
  useEditBlock,
  useLetter,
  usePdfPreview,
  useRender,
  useSpellcheck,
  type Letter,
} from './api'
import { BlockEditor } from './BlockEditor'
import { editorBlocks, ideasFor, type EditorBlock as Block } from './blocks'
import { RecipientPanel } from './RecipientPanel'
import { SignaturePanel } from '@/features/signature/SignaturePanel'
import { ExportButtons, QualityPanel, VersionsPanel } from './panels'
import { activeIssues, applyAll, applyIssue, isStale, type Checked } from './spellcheck'

type Drafts = Record<string, string>

export function LetterPage() {
  const { letterId = '' } = useParams()
  // Keyed by id: drafts and spelling results never leak from one letter to the next.
  return <LetterEditor key={letterId} letterId={letterId} />
}

function useLetterRender(letterId: string, pdfDocumentId: string | null) {
  const qc = useQueryClient()
  const render = useRender(letterId)
  const task = useTask(render.data?.task_id, 500) // renders take ~2 s: poll fast
  const pdf = usePdfPreview(letterId, pdfDocumentId)
  const status = task.data?.status
  useEffect(() => {
    if (status === 'done') qc.invalidateQueries({ queryKey: ['letter', letterId] })
  }, [status, qc, letterId])
  const rendering = render.isPending || status === 'queued'
  const renderFailed = status === 'failed' || render.isError
  return { render, pdf, rendering, renderFailed }
}

function useSpelling(letterId: string, setDrafts: Dispatch<SetStateAction<Drafts>>) {
  // Spelling results, each tied to the text it was computed for (see `activeIssues`).
  const [checked, setChecked] = useState<Record<string, Checked>>({})
  const spell = useSpellcheck(letterId)
  // One call checks several paragraphs (the whole letter) or just one. A result is stored with
  // the text it was computed for: if the user typed meanwhile it shows as "edited since the
  // last check" rather than vanishing.
  const check = (items: { key: string; text: string }[]) => {
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
  return { checked, spell, check, keep, accept, checking, errorKeys }
}
type Spelling = ReturnType<typeof useSpelling>

function LetterEditor({ letterId }: { letterId: string }) {
  const t = useT()
  const navigate = useNavigate()
  const letter = useLetter(letterId)
  const edit = useEditBlock(letterId)
  const { render, pdf, rendering, renderFailed } = useLetterRender(
    letterId,
    letter.data?.pdf_document_id ?? null,
  )
  // Unsaved edits only; everything else is read from the server copy.
  const [drafts, setDrafts] = useState<Drafts>({})
  const spelling = useSpelling(letterId, setDrafts)

  const back = { to: '/letters', label: t('letters.title') }
  if (letter.isPending)
    return (
      <Page title={t('letters.page.title')} back={back}>
        <ListSkeleton />
      </Page>
    )
  if (letter.isError)
    return (
      <Page title={t('letters.page.title')} back={back}>
        <ErrorMessage error={letter.error} />
      </Page>
    )

  // A letter the user writes themself starts with empty paragraphs: no PDF until they are done.
  const incomplete = editorBlocks(letter.data.content, t).some(
    (b) => b.block !== 'subject' && !b.text.trim(),
  )

  return (
    <Page
      title={letter.data.content.subject || t('letters.page.title')}
      description={letter.data.ideas ? t('letters.page.desc_own') : t('letters.page.desc_ai')}
      back={back}
      wide
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            loading={rendering}
            disabled={incomplete}
            title={incomplete ? t('letters.page.write_first') : undefined}
            onClick={() => render.mutate()}
          >
            {rendering ? t('letters.page.rendering') : t('letters.page.render')}
          </Button>
          <DeleteLetterButton id={letterId} onDeleted={() => navigate('/letters')} />
          {letter.data.job_id && (
            <ApplyActions jobId={letter.data.job_id} pdfDocumentId={letter.data.pdf_document_id} />
          )}
        </div>
      }
    >
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-2">
        <EditColumn
          letterId={letterId}
          letter={letter.data}
          drafts={drafts}
          setDrafts={setDrafts}
          edit={edit}
          spelling={spelling}
        />
        <div className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <ExportButtons letterId={letterId} />
          {rendering && <StepProgress steps={[t('letters.page.typesetting')]} />}
          <PreviewPane pdf={pdf} render={render} renderFailed={renderFailed} />
          <QualityPanel letterId={letterId} />
          <VersionsPanel letterId={letterId} onRestored={() => setDrafts({})} />
        </div>
      </div>
    </Page>
  )
}

// Several paragraphs corrected at once would otherwise need one Save each.
async function saveAll(
  unsaved: Block[],
  drafts: Drafts,
  setDrafts: Dispatch<SetStateAction<Drafts>>,
  edit: ReturnType<typeof useEditBlock>,
) {
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

function EditColumn({
  letterId,
  letter,
  drafts,
  setDrafts,
  edit,
  spelling,
}: {
  letterId: string
  letter: Letter
  drafts: Drafts
  setDrafts: Dispatch<SetStateAction<Drafts>>
  edit: ReturnType<typeof useEditBlock>
  spelling: Spelling
}) {
  const t = useT()
  const { checked, spell, keep, accept, checking, errorKeys } = spelling
  const blocks = editorBlocks(letter.content, t)
  const textOf = (b: Block) => drafts[b.key] ?? b.text
  const issuesOf = (b: Block) => activeIssues(checked[b.key], textOf(b))
  const checkable = blocks.filter((b) => textOf(b).trim())
  const check = (keys: string[]) =>
    spelling.check(
      checkable.filter((b) => keys.includes(b.key)).map((b) => ({ key: b.key, text: textOf(b) })),
    )
  const unsaved = blocks.filter((b) => drafts[b.key] !== undefined && drafts[b.key] !== b.text)

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{t('letters.page.ai_note')}</p>
      <CheckToolbar
        spell={spell}
        checkingAll={spell.isPending && checking.length > 1}
        checkable={checkable.length}
        checkedCount={checkable.filter((b) => issuesOf(b) !== undefined).length}
        issueCount={blocks.flatMap((b) => issuesOf(b) ?? []).length}
        unsaved={unsaved.length}
        saving={edit.isPending}
        onCheckAll={() => check(blocks.map((b) => b.key))}
        onApplyAll={() =>
          blocks.forEach((b) => {
            const issues = issuesOf(b)
            if (issues?.length) accept(b, applyAll(textOf(b), issues), [])
          })
        }
        onSaveAll={() => saveAll(unsaved, drafts, setDrafts, edit)}
      />
      {spell.isError && errorKeys.length > 1 && <ErrorMessage error={spell.error} />}
      <RecipientPanel key={JSON.stringify(letter.content.recipient)} letter={letter} />
      <SignaturePanel letter={letter} />
      {blocks.map((b) => (
        <BlockEditor
          key={b.key}
          letterId={letterId}
          block={b}
          value={drafts[b.key] ?? b.text}
          ideas={ideasFor(letter.ideas, b, t)}
          issues={issuesOf(b)}
          ignored={checked[b.key]?.ignored}
          staleCheck={isStale(checked[b.key], textOf(b))}
          checking={checking.includes(b.key)}
          checkDisabled={spell.isPending}
          checkError={errorKeys.length === 1 && errorKeys[0] === b.key ? spell.error : undefined}
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
  )
}

function CheckToolbar({
  spell,
  checkingAll,
  checkable,
  checkedCount,
  issueCount,
  unsaved,
  saving,
  onCheckAll,
  onApplyAll,
  onSaveAll,
}: {
  spell: Spelling['spell']
  checkingAll: boolean
  checkable: number
  checkedCount: number
  issueCount: number
  unsaved: number
  saving: boolean
  onCheckAll: () => void
  onApplyAll: () => void
  onSaveAll: () => void
}) {
  const t = useT()
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        size="sm"
        variant="outline"
        loading={checkingAll}
        disabled={spell.isPending || checkable === 0}
        onClick={onCheckAll}
      >
        {checkingAll ? t('letters.page.checking_all') : t('letters.page.check_all')}
      </Button>
      {issueCount > 1 && (
        <Button size="sm" variant="outline" onClick={onApplyAll}>
          {t('letters.page.apply_all', { n: issueCount })}
        </Button>
      )}
      {unsaved > 1 && (
        <Button size="sm" loading={saving} onClick={onSaveAll}>
          {saving ? t('letters.page.saving') : t('letters.page.save_n', { n: unsaved })}
        </Button>
      )}
      <span role="status" aria-live="polite" className="text-sm text-muted-foreground">
        {checkedCount === 0
          ? ''
          : checkedCount < checkable
            ? issueCount === 0
              ? t('letters.page.progress_none', {
                  done: checkedCount,
                  total: checkable,
                })
              : t('letters.page.progress', {
                  done: checkedCount,
                  total: checkable,
                  count: issueCount,
                })
            : issueCount === 0
              ? t('letters.spell.none')
              : t('letters.page.below', { count: issueCount })}
      </span>
    </div>
  )
}

function PreviewPane({
  pdf,
  render,
  renderFailed,
}: {
  pdf: ReturnType<typeof usePdfPreview>
  render: ReturnType<typeof useRender>
  renderFailed: boolean
}) {
  const t = useT()
  return (
    <>
      {pdf.failed && (
        <p role="alert" className="text-sm text-destructive">
          {t('letters.page.pdf_failed')}
        </p>
      )}
      {renderFailed && (
        <p role="alert" className="text-sm text-destructive">
          {render.isError ? describeError(render.error) : t('letters.page.render_failed')}
        </p>
      )}
      {pdf.url ? (
        <iframe
          title={t('letters.page.preview_title')}
          src={pdf.url}
          className="h-[70vh] w-full rounded-xl border bg-white shadow-xs"
        />
      ) : (
        <EmptyState
          icon={FileText}
          title={t('letters.page.no_preview')}
          description={t('letters.page.no_preview_desc')}
        />
      )}
    </>
  )
}
