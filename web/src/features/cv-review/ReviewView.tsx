import { Download } from 'lucide-react'
import { useContext, useEffect, useMemo, useState } from 'react'
import { useBlocker } from 'react-router'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Modal } from '@/components/Modal'
import { ScoreRing } from '@/components/ScoreRing'
import { StepProgress } from '@/components/StepProgress'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useT } from '@/i18n'
import { downloadBlob } from '@/lib/download'
import { cn } from 'cn'
import { BlockRow, CommentCard, DimensionRow, LineLink } from './Evidence'
import { PdfView } from './PdfView'
import {
  criterion,
  ViewCtx,
  type Block,
  type Comment,
  type Pin,
  useRecheck,
  usePdfLayout,
  useReview,
  useReviewRun,
  type Level,
  type Review,
  type Track,
} from './api'

const LINK = 'underline-offset-2 hover:underline focus-visible:ring-3 focus-visible:ring-ring/50'

/** Warns before leaving with unsaved edits (they live only in this page). */
function Leave({ block }: { block: boolean }) {
  const t = useT()
  useEffect(() => {
    if (!block) return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [block])
  const blocker = useBlocker(block)
  return (
    <Modal open={blocker.state === 'blocked'} label={t('cvr.leave.title')}>
      <h2 className="font-semibold">{t('cvr.leave.title')}</h2>
      <p className="mt-2 text-sm text-muted-foreground">{t('cvr.leave.body')}</p>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="outline" onClick={() => blocker.reset?.()}>
          {t('cvr.leave.stay')}
        </Button>
        <Button variant="destructive" onClick={() => blocker.proceed?.()}>
          {t('cvr.leave.go')}
        </Button>
      </div>
    </Modal>
  )
}

const MD_PREFIX: Record<string, string> = { heading: '\n## ', bullet: '- ' }

export function ReviewView({ review }: { review: Review }) {
  const t = useT()
  const { blocks, comments, dimensions, summary } = review.data
  const original = useMemo(() => Object.fromEntries(blocks.map((b) => [b.id, b.text])), [blocks])
  const [texts, setTexts] = useState(original)
  const [tab, setTab] = useState<'cv' | 'comments'>('cv')

  const byId = useMemo(() => Object.fromEntries(comments.map((c) => [c.block_id, c])), [comments])
  const dirty = blocks.some((b) => texts[b.id] !== original[b.id])
  const { body, recheck, live, fresh } = useLiveCheck(review, texts, dirty)
  const { run, running: evaluating, error } = useReviewRun()
  const { sel, pin, cites, choose } = useSelection(byId)

  const view = {
    texts,
    original,
    setText: (id: string, text: string) => setTexts((x) => ({ ...x, [id]: text })),
    lineOf: (id: string) => blocks.findIndex((b) => b.id === id) + 1,
    sel,
    pin,
    cites,
    select: (id: string, p: Pin | null = null, toCv = false) => {
      choose(id, p)
      if (toCv) setTab('cv')
    },
  }

  return (
    <ViewCtx value={view}>
      <Leave block={dirty && !evaluating} />
      <Card>
        <CardContent className="space-y-4">
          <ScoreHeader
            review={review}
            score={fresh?.score ?? review.score}
            fresh={!!fresh}
            evaluating={evaluating}
            onReeval={() => run({ parent_review_id: review.id, ...body })}
            blocks={body.blocks}
          />
          {evaluating && (
            <StepProgress steps={[t('cvr.step_read'), t('cvr.step_check'), t('cvr.step_write')]} />
          )}
          {review.data.truncated && (
            <p className="text-sm text-muted-foreground">{t('cvr.truncated')}</p>
          )}
          <ErrorMessage error={error ?? recheck.error} />
          <section aria-label={t('cvr.dimensions')}>
            <ul className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
              {Object.entries(dimensions)
                .sort(([a, x], [b, y]) => y.weight - x.weight || a.localeCompare(b))
                .map(([name, d]) => (
                  <DimensionRow
                    key={name}
                    name={name}
                    d={d}
                    v={Math.round(fresh?.dimensions[name] ?? d.score)}
                  />
                ))}
            </ul>
          </section>
          <SummaryLists summary={summary} />
        </CardContent>
      </Card>

      <Tabs tab={tab} setTab={setTab} />

      <div className="grid gap-4 lg:grid-cols-2">
        <CvColumn review={review} hidden={tab !== 'cv'} byId={byId} />
        <section
          aria-label={t('cvr.col.comments')}
          className={cn('space-y-3', tab !== 'comments' && 'max-lg:hidden')}
        >
          <h2 className="text-sm font-semibold">{t('cvr.col.comments')}</h2>
          {blocks
            .flatMap((b) => byId[b.id] ?? [])
            .map((c) => (
              <CommentCard
                key={c.block_id}
                c={c}
                weight={dimensions[criterion(c.criterion).dim]?.weight}
                signals={live?.signals[c.block_id] ?? []}
              />
            ))}
        </section>
      </div>
    </ViewCtx>
  )
}

/** Live, rules-only feedback on the edited text; scores follow the edits only once rechecked. */
function useLiveCheck(review: Review, texts: Record<string, string>, dirty: boolean) {
  const { blocks } = review.data
  // Empty lines are left out of the recheck, the re-evaluation and the download.
  const body = useMemo(
    () => ({
      blocks: blocks.flatMap((b) => (texts[b.id].trim() ? [{ ...b, text: texts[b.id] }] : [])),
      track: review.track as Track,
      level: review.level as Level,
    }),
    [blocks, texts, review.track, review.level],
  )

  // Live, rules-only feedback: 600 ms after the last keystroke (and once on open, for the chips).
  const recheck = useRecheck()
  const { mutate } = recheck
  useEffect(() => {
    const h = setTimeout(() => mutate(body), 600)
    return () => clearTimeout(h)
  }, [body, mutate])
  const live = recheck.data
  const fresh = dirty ? live : undefined // scores follow the edits only once rechecked
  return { body, recheck, live, fresh }
}

/** The comment picked, the evidence chip last clicked, and scrolling both into view. */
function useSelection(byId: Record<string, Comment>) {
  const [sel, setSel] = useState<string | null>(null)
  const [pin, setPin] = useState<Pin | null>(null) // the evidence chip last clicked
  const selected = sel ? byId[sel] : undefined
  // Automatic (rule) comments highlight nothing.
  const cites = selected?.source === 'rule' ? [] : (selected?.citations ?? [])
  useEffect(() => {
    if (!sel) return
    const first = selected?.citations[0]?.block_id
    for (const id of [`block-${pin?.b ?? first ?? sel}`, `comment-${sel}`])
      document.getElementById(`cvr-${id}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [sel, pin, selected])
  const choose = (id: string, p: Pin | null) => {
    setSel(id)
    setPin(p)
  }
  return { sel, pin, cites, choose }
}

function ScoreHeader({
  review,
  score,
  fresh,
  evaluating,
  onReeval,
  blocks,
}: {
  review: Review
  score: number
  fresh: boolean
  evaluating: boolean
  onReeval: () => void
  blocks: Block[]
}) {
  const t = useT()
  const parent = useReview(review.parent_id).data
  const delta = parent ? Math.round(review.score - parent.score) : null
  return (
    <div className="flex flex-wrap items-center gap-6">
      <ScoreRing score={score} />
      <div className="min-w-0 flex-1 space-y-1">
        <p aria-live="polite" className="text-sm font-medium">
          {fresh ? t('cvr.live_score') : t('cvr.ai_score')}: {Math.round(score)}
        </p>
        {delta !== null && (
          <p className="text-sm text-muted-foreground">
            {t('cvr.delta', { delta: delta > 0 ? `+${delta}` : `${delta}` })}
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button loading={evaluating} onClick={onReeval}>
          {t('cvr.reeval')}
        </Button>
        <Button
          variant="outline"
          onClick={() =>
            downloadBlob(
              'cv-edited.md',
              'text/markdown',
              blocks
                .map((b) => (MD_PREFIX[b.kind] ?? '') + b.text)
                .join('\n')
                .trim() + '\n',
            )
          }
        >
          <Download /> {t('cvr.download')}
        </Button>
      </div>
    </div>
  )
}

function SummaryLists({ summary }: { summary: Review['data']['summary'] }) {
  const t = useT()
  const { texts, select } = useContext(ViewCtx)
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {summary.strengths.length > 0 && (
        <section>
          <h2 className="mb-1 text-sm font-semibold">{t('cvr.strengths')}</h2>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {summary.strengths.map((s, i) => (
              <li key={i}>
                {s.text} {s.block_id && <LineLink id={s.block_id} />}
              </li>
            ))}
          </ul>
        </section>
      )}
      {summary.top_fixes.length > 0 && (
        <section>
          <h2 className="mb-1 text-sm font-semibold">{t('cvr.top_fixes')}</h2>
          <ul className="space-y-1 text-sm">
            {summary.top_fixes.map((id) => (
              <li key={id}>
                <button
                  type="button"
                  className={cn('text-left', LINK)}
                  onClick={() => select(id, null, true)}
                >
                  {(texts[id] ?? '').slice(0, 60)}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function Tabs({
  tab,
  setTab,
}: {
  tab: 'cv' | 'comments'
  setTab: (tab: 'cv' | 'comments') => void
}) {
  const t = useT()
  return (
    <div role="tablist" className="flex gap-2 lg:hidden">
      {(['cv', 'comments'] as const).map((k) => (
        <Button
          key={k}
          role="tab"
          aria-selected={tab === k}
          variant={tab === k ? 'default' : 'outline'}
          size="sm"
          onClick={() => setTab(k)}
        >
          {t(`cvr.tab.${k}`)}
        </Button>
      ))}
    </div>
  )
}

function CvColumn({
  review,
  hidden,
  byId,
}: {
  review: Review
  hidden: boolean
  byId: Record<string, Comment>
}) {
  const t = useT()
  const { blocks } = review.data
  const [mode, setMode] = useState<'pdf' | 'text'>('pdf')
  const layout = usePdfLayout(review.id)
  const pdf = layout.data // only for a PDF upload
  return (
    <section aria-label={t('cvr.col.cv')} className={cn('space-y-1', hidden && 'max-lg:hidden')}>
      <h2 className="sr-only">{t('cvr.col.cv')}</h2>
      {pdf && (
        <div className="flex gap-2">
          {(['pdf', 'text'] as const).map((k) => (
            <Button
              key={k}
              aria-pressed={mode === k}
              variant={mode === k ? 'default' : 'outline'}
              size="sm"
              onClick={() => setMode(k)}
            >
              {t(`cvr.view.${k}`)}
            </Button>
          ))}
        </div>
      )}
      {pdf && mode === 'pdf' ? (
        <PdfView reviewId={review.id} layout={pdf} blocks={blocks} byId={byId} />
      ) : layout.isPending ? null : (
        blocks.map((b) => <BlockRow key={b.id} b={b} c={byId[b.id]} />)
      )}
    </section>
  )
}
