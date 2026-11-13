import { CircleCheck, CircleX, Minus, TriangleAlert, Undo2 } from 'lucide-react'
import { useContext, useState, type ReactNode } from 'react'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useT, type Key } from '@/i18n'
import { cn } from 'cn'
import {
  criterion,
  ViewCtx,
  type Block,
  type Comment,
  type Criterion,
  type Quote,
  type Review,
} from './api'

/** Colour is never the only cue: each rating also has an icon and a word. */
const RATING = {
  good: { icon: CircleCheck, tone: 'success', box: 'border-l-success bg-success/5' },
  moderate: { icon: TriangleAlert, tone: 'warning', box: 'border-l-warning bg-warning/5' },
  poor: { icon: CircleX, tone: 'danger', box: 'border-l-destructive bg-destructive/5' },
} as const
const FOCUS = 'focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none'
const MAX_LINKS = 8

export function LineLink({ id }: { id: string }) {
  const t = useT()
  const { lineOf, select } = useContext(ViewCtx)
  return (
    <button
      type="button"
      className={cn('underline-offset-2 hover:underline', FOCUS)}
      onClick={() => select(id, null, true)}
    >
      {t('cvr.line', { n: lineOf(id) })}
    </button>
  )
}

/** The passages of `text` cited by `quotes` (indexOf in the CURRENT text), highlighted with <mark>.
 *  Overlaps: the pinned quote wins, then the earliest. */
function Marked({ text, quotes, pin }: { text: string; quotes: Quote[]; pin: string | null }) {
  const picked: { i: number; end: number; pinned: boolean }[] = []
  const all = quotes.flatMap((q) => {
    const i = text.indexOf(q.quote)
    return i < 0 ? [] : [{ i, end: i + q.quote.length, pinned: pin === q.quote }]
  })
  for (const r of all.sort((a, b) => +b.pinned - +a.pinned || a.i - b.i))
    if (!picked.some((p) => r.i < p.end && p.i < r.end)) picked.push(r)
  const out: ReactNode[] = []
  let at = 0
  for (const r of picked.sort((a, b) => a.i - b.i)) {
    const cls = r.pinned ? 'bg-primary/30 ring-1 ring-primary' : 'bg-warning/40'
    out.push(
      text.slice(at, r.i),
      <mark key={r.i} className={cn('rounded-sm text-foreground', cls)}>
        {text.slice(r.i, r.end)}
      </mark>,
    )
    at = r.end
  }
  return <>{out.concat(text.slice(at))}</>
}

/** "Based on" chip: the rubric point, what good looks like, its weight at this level, and the source. */
function CriterionPanel({ id, weight }: { id: Criterion; weight: number | undefined }) {
  const t = useT()
  const c = criterion(id)
  return (
    <details className="rounded-md border bg-background/60 text-xs">
      <summary className={cn('cursor-pointer px-2 py-1 font-medium', FOCUS)}>
        {t('cvr.based_on')}: {t(`cvr.crit.${id}.title`)}
      </summary>
      <div className="space-y-1 px-2 pb-2 text-muted-foreground">
        <p>
          <strong>{t('cvr.good_looks')}: </strong>
          {t(`cvr.crit.${id}.good`)}
        </p>
        {weight !== undefined && <p>{t('cvr.weight', { w: Math.round(weight) })}</p>}
        <p>
          {t('cvr.source')}:{' '}
          <a href={c.url} target="_blank" rel="noopener noreferrer" className="underline">
            {c.source}
          </a>
        </p>
      </div>
    </details>
  )
}

export function DimensionRow({
  name,
  d,
  v,
}: {
  name: string
  d: Review['data']['dimensions'][string]
  v: number
}) {
  const t = useT()
  const ids = d.block_ids ?? []
  return (
    <li className="text-sm">
      <details>
        <summary className={cn('cursor-pointer', FOCUS)}>
          <span className="inline-flex w-[calc(100%-1.25rem)] justify-between gap-2 align-top">
            <span>{t(`cvr.dim.${name}` as Key)}</span>
            <span className="text-muted-foreground">
              {v} · {t('cvr.weight', { w: Math.round(d.weight) })}
            </span>
          </span>
          <div aria-hidden className="mt-1 h-1.5 rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary" style={{ width: `${v}%` }} />
          </div>
        </summary>
        <div className="mt-1 space-y-1 text-xs text-muted-foreground">
          {d.reason && (
            <p>
              <strong>{t('cvr.why_score')}: </strong>
              {d.reason}
            </p>
          )}
          {ids.length > 0 && (
            <p className="flex flex-wrap gap-x-2">
              {!d.reason && <strong>{t('cvr.lowered_by')}:</strong>}
              {ids.slice(0, MAX_LINKS).map((id) => (
                <LineLink key={id} id={id} />
              ))}
              {ids.length > MAX_LINKS && <span>+{ids.length - MAX_LINKS}</span>}
            </p>
          )}
        </div>
      </details>
    </li>
  )
}

export function CommentCard({
  c,
  weight,
  signals,
}: {
  c: Comment
  weight: number | undefined
  signals: string[]
}) {
  const t = useT()
  const { texts, setText, lineOf, sel, select } = useContext(ViewCtx)
  const [prev, setPrev] = useState<string>() // text before "Use rewrite"
  const { block_id: id, rewrite } = c
  const r = RATING[c.rating]
  const Icon = r.icon
  const ring = sel === id
  return (
    <article
      id={`cvr-comment-${id}`}
      className={cn(
        'space-y-2 rounded-md border border-l-4 p-3 text-sm',
        r.box,
        ring && 'ring-2 ring-ring',
      )}
    >
      <button
        type="button"
        aria-pressed={ring}
        onClick={() => select(id)}
        className={cn('flex w-full items-center gap-2 text-left', FOCUS)}
      >
        <StatusBadge tone={r.tone}>
          <Icon aria-hidden className="mr-1 size-3" />
          {t(`cvr.rating.${c.rating}`)}
        </StatusBadge>
        <span className="min-w-0 flex-1 truncate text-muted-foreground">
          {(texts[id] ?? '').slice(0, 60)}
        </span>
      </button>
      {c.source === 'rule' && <StatusBadge tone="info">{t('cvr.rule')}</StatusBadge>}
      <CriterionPanel id={c.criterion} weight={weight} />
      {c.citations.length > 0 ? (
        <ol aria-label={t('cvr.evidence')} className="flex flex-wrap gap-1">
          {c.citations.map((q, n) => (
            <li key={n}>
              <button
                type="button"
                className={cn(
                  'max-w-full rounded-md border bg-background px-2 py-1 text-left text-xs',
                  FOCUS,
                )}
                onClick={() => select(id, { b: q.block_id, q: q.quote }, true)}
              >
                [{n + 1}] <q>{q.quote.slice(0, 60)}</q> · {t('cvr.line', { n: lineOf(q.block_id) })}
                {!texts[q.block_id]?.includes(q.quote) && (
                  <span className="ml-1 font-medium">({t('cvr.outdated')})</span>
                )}
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-xs text-muted-foreground">{t('cvr.no_quote')}</p>
      )}
      {signals.length > 0 && (
        <ul className="flex flex-wrap gap-1">
          {signals.map((s) => (
            <li key={s}>
              <StatusBadge tone="warning">{t(`cvr.signal.${s}` as Key)}</StatusBadge>
            </li>
          ))}
        </ul>
      )}
      {(['why', 'improve'] as const).map(
        (k) =>
          c[k] && (
            <p key={k}>
              <strong>{t(`cvr.${k}`)}: </strong>
              {c[k]}
            </p>
          ),
      )}
      {rewrite && (
        <div className="space-y-1 rounded bg-muted/60 p-2">
          <p className="text-xs font-medium">{t('cvr.rewrite')}</p>
          <p>{rewrite}</p>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => {
                setPrev(texts[id])
                setText(id, rewrite)
              }}
            >
              {t('cvr.use_rewrite')}
            </Button>
            {prev !== undefined && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setText(id, prev)
                  setPrev(undefined)
                }}
              >
                <Undo2 /> {t('cvr.undo')}
              </Button>
            )}
          </div>
        </div>
      )}
    </article>
  )
}

/** One CV line. Read mode (highlighted quotes) and the textarea never swap because of a selection:
 *  only `editing` (click/Enter/Space on the read view, or focusing the textarea) opens the textarea. */
export function BlockRow({ b, c }: { b: Block; c: Comment | undefined }) {
  const t = useT()
  const { texts, original, setText, lineOf, sel, pin, cites, select } = useContext(ViewCtx)
  const [editing, setEditing] = useState(false)
  const text = texts[b.id]
  const n = lineOf(b.id)
  const mine = cites.filter((q) => q.block_id === b.id)
  const quotes = mine.filter((q) => text.includes(q.quote))
  const r = c && RATING[c.rating]
  const Icon = r?.icon ?? Minus
  const look = cn(
    b.kind === 'heading' && 'text-base font-semibold uppercase tracking-wide md:text-base',
    b.kind === 'bullet' && 'pl-4',
  )
  const edit = (on: boolean) => {
    setEditing(on)
    if (on) select(b.id)
  }
  return (
    <div
      id={`cvr-block-${b.id}`}
      className={cn(
        'rounded-md border-l-4 px-3 py-2',
        r?.box ?? 'border-l-border',
        (sel === b.id || mine.length > 0) && 'ring-2 ring-ring',
      )}
    >
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <Icon aria-hidden className="size-3" />
        {c ? t(`cvr.rating.${c.rating}`) : t('cvr.rating.none')} · {t('cvr.line', { n })}
      </div>
      {quotes.length > 0 && !editing ? (
        <button
          type="button"
          aria-label={t('cvr.block', { n })}
          onClick={() => edit(true)}
          className={cn('w-full px-1 py-0.5 text-left text-sm whitespace-pre-wrap', FOCUS, look)}
        >
          <Marked text={text} quotes={quotes} pin={pin?.b === b.id ? pin.q : null} />
        </button>
      ) : (
        <Textarea
          aria-label={t('cvr.block', { n })}
          rows={1}
          maxLength={600}
          autoFocus={editing} // focus follows the click/Enter that opened it
          value={text}
          onFocus={() => edit(true)}
          onBlur={() => edit(false)}
          onChange={(e) => setText(b.id, e.target.value)}
          className={cn('min-h-0 border-transparent bg-transparent px-1 py-0.5 shadow-none', look)}
        />
      )}
      {text !== original[b.id] && (
        <p className="text-xs text-muted-foreground">{t('cvr.edited')}</p>
      )}
    </div>
  )
}
