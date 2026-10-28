import { useRef } from 'react'
import { Button } from '@/components/ui/button'
import { useT } from '@/i18n'
import type { SpellIssue } from './spellcheck'

const CONTEXT = 24 // characters of text shown around a correction

type Props = {
  label: string
  /** The text the issues were computed for (the paragraph's current text). */
  value: string
  /** `undefined` = not checked yet. */
  issues?: SpellIssue[]
  ignored?: number
  /** Checked, then edited: the old result no longer applies. */
  stale: boolean
  /** The paragraph has changes that are not saved yet. */
  unsaved: boolean
  onApplyIssue: (index: number) => void
  onApplyAll: () => void
  onIgnoreIssue: (index: number) => void
  /** Put the caret in the paragraph (after the text just corrected). */
  onFocusText: (caret: number) => void
}

/** The corrections of one paragraph. The outer live region is always mounted, so screen
 *  readers announce what appears in it. */
export function SpellPanel({
  label,
  value,
  issues,
  ignored = 0,
  stale,
  unsaved,
  onApplyIssue,
  onApplyAll,
  onIgnoreIssue,
  onFocusText,
}: Props) {
  const t = useT()
  const root = useRef<HTMLDivElement>(null)
  // Applying removes the button that was clicked: keep the keyboard user's place.
  const afterChange = (caret?: number) =>
    setTimeout(() => {
      const next = root.current?.querySelector<HTMLButtonElement>('[data-apply]')
      if (next) next.focus()
      else if (caret !== undefined) onFocusText(caret)
    }, 0)

  return (
    <div
      ref={root}
      role="status"
      aria-live="polite"
      aria-label={t('letters.spell.aria', { label })}
    >
      {stale && (
        <p className="rounded-md border border-dashed p-2 text-sm text-muted-foreground">
          {t('letters.spell.stale')}
        </p>
      )}
      {!stale && issues !== undefined && (
        <div className="space-y-2 rounded-md border p-2 text-sm">
          {issues.length === 0 ? (
            <p className={unsaved ? 'font-medium' : 'text-muted-foreground'}>
              {unsaved
                ? t('letters.spell.applied')
                : ignored > 0
                  ? t('letters.spell.no_more', { n: ignored })
                  : t('letters.spell.none')}
            </p>
          ) : (
            <>
              <p className="font-medium">
                {t('letters.spell.suggested', { count: issues.length })}
              </p>
              <ul className="space-y-3">
                {issues.map((issue, i) => (
                  <li key={`${issue.start}-${issue.wrong}`} className="space-y-1">
                    <p>
                      <span className="rounded bg-destructive/10 px-1 line-through">
                        {issue.wrong}
                      </span>{' '}
                      →{' '}
                      <span className="rounded bg-success/15 px-1 font-medium">{issue.right}</span>
                      {issue.reason && (
                        <span className="text-muted-foreground"> · {issue.reason}</span>
                      )}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      …{value.slice(Math.max(0, issue.start - CONTEXT), issue.start)}
                      <b className="text-foreground">{issue.wrong}</b>
                      {value.slice(issue.end, issue.end + CONTEXT)}…
                    </p>
                    <div className="flex gap-3">
                      <Button
                        size="sm"
                        data-apply
                        aria-label={t('letters.spell.apply_aria', {
                          i: i + 1,
                          total: issues.length,
                          wrong: issue.wrong,
                          right: issue.right,
                        })}
                        onClick={() => {
                          onApplyIssue(i)
                          afterChange(issue.start + issue.right.length)
                        }}
                      >
                        {t('letters.spell.apply')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        aria-label={t('letters.spell.ignore_aria', {
                          i: i + 1,
                          total: issues.length,
                          wrong: issue.wrong,
                        })}
                        onClick={() => {
                          onIgnoreIssue(i)
                          afterChange()
                        }}
                      >
                        {t('letters.spell.ignore')}
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
              {issues.length > 1 && (
                <Button
                  size="sm"
                  variant="outline"
                  aria-label={t('letters.spell.apply_all_aria', { n: issues.length, label })}
                  onClick={() => {
                    onApplyAll()
                    afterChange()
                  }}
                >
                  {t('letters.spell.apply_all', { n: issues.length })}
                </Button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
