import { useContext, useEffect } from 'react'
import { useT } from '@/i18n'
import { cn } from 'cn'
import { usePdfPage, ViewCtx, type Block, type Comment, type PdfLayout } from './api'

const TINT = {
  good: 'bg-success/10 hover:bg-success/25',
  moderate: 'bg-warning/15 hover:bg-warning/30',
  poor: 'bg-destructive/10 hover:bg-destructive/25',
}
const pos = (x: number, y: number, w: number, h: number) => ({
  left: `${x * 100}%`,
  top: `${y * 100}%`,
  width: `${w * 100}%`,
  height: `${h * 100}%`,
})

/** The user's own PDF, one image per page, with every block marked where it is printed (tinted by
 *  rating) and the cited passage of the selected comment highlighted. Read-only: edit in the text view. */
export function PdfView({
  reviewId,
  layout,
  blocks,
  byId,
}: {
  reviewId: string
  layout: PdfLayout
  blocks: Block[]
  byId: Record<string, Comment>
}) {
  const t = useT()
  const { texts, original, sel, pin, cites, select, lineOf } = useContext(ViewCtx)
  // The mark the scroll below looks for: the first highlighted piece, else the selected block's first line.
  useEffect(() => {
    document.querySelector('[data-cvr-focus]')?.scrollIntoView?.({ block: 'center' })
  }, [sel, pin])

  const shown = blocks.filter((b) => layout.boxes[b.id] && texts[b.id] === original[b.id])
  return (
    <div className="space-y-3">
      {shown.length < blocks.length && (
        <p className="text-xs text-muted-foreground">{t('cvr.pdf.note')}</p>
      )}
      {layout.ratios.map((ratio, p) => (
        <Page key={p} reviewId={reviewId} n={p + 1} ratio={ratio}>
          {shown.flatMap((b) => {
            const c = byId[b.id]
            const lines = layout.boxes[b.id].filter((l) => l.p === p)
            const text = original[b.id]
            const quotes = (
              pin?.b === b.id
                ? [pin.q]
                : cites.filter((q) => q.block_id === b.id).map((q) => q.quote)
            ).filter((q) => text.includes(q))
            return lines.flatMap((l, i) => {
              // the part of this line the quote covers, as fractions of the line
              const hits = quotes.flatMap((q) => {
                const from = Math.max(text.indexOf(q), l.s)
                const to = Math.min(text.indexOf(q) + q.length, l.e)
                return from < to ? [[(from - l.s) / (l.e - l.s), (to - l.s) / (l.e - l.s)]] : []
              })
              return [
                // A mouse shortcut only: printed lines are smaller than a 24 px target (WCAG 2.5.8),
                // and the comment cards and the text view do the same from the keyboard.
                <span
                  key={`${b.id}-${i}`}
                  aria-hidden
                  data-cvr-block={b.id}
                  data-cvr-focus={sel === b.id && !hits.length ? '' : undefined}
                  title={t('cvr.block', { n: lineOf(b.id) })}
                  onClick={() => select(b.id)}
                  style={pos(l.x, l.y, l.w, l.h)}
                  className={cn(
                    'absolute cursor-pointer rounded-sm',
                    c ? TINT[c.rating] : 'hover:bg-muted/40',
                    sel === b.id && 'ring-2 ring-ring',
                  )}
                />,
                ...hits.map(([a, z], j) => (
                  <span
                    key={`${b.id}-${i}-${j}`}
                    data-cvr-focus=""
                    aria-hidden
                    style={pos(l.x + l.w * a, l.y, l.w * (z - a), l.h)}
                    className="pointer-events-none absolute rounded-sm bg-primary/30 ring-1 ring-primary"
                  />
                )),
              ]
            })
          })}
        </Page>
      ))}
    </div>
  )
}

function Page({
  reviewId,
  n,
  ratio,
  children,
}: {
  reviewId: string
  n: number
  ratio: number
  children: React.ReactNode
}) {
  const src = usePdfPage(reviewId, n).data
  return (
    <div
      className="relative w-full overflow-hidden rounded-md border bg-muted"
      style={{ aspectRatio: `${1 / ratio}` }}
    >
      {src && <img src={src} alt="" className="absolute inset-0 size-full" />}
      {children}
    </div>
  )
}
