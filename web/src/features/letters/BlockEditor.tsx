import { useRef, useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Spinner } from '@/components/Spinner'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useT } from '@/i18n'
import { useAssist, type AssistAction } from './api'
import type { EditorBlock } from './blocks'
import { SpellPanel } from './SpellPanel'
import type { SpellIssue } from './spellcheck'

const ACTIONS: AssistAction[] = [
  'shorten',
  'more_formal',
  'more_concrete',
  'add_metric',
  'fix_grammar',
]

type Range = { start: number; end: number }

type Props = {
  letterId: string
  block: EditorBlock
  /** Current text: the unsaved draft if there is one, else the stored text. */
  value: string
  /** Writing ideas for this block (letters the user writes themself). */
  ideas?: string[]
  /** Spelling: `undefined` = not checked (or edited since), `[]` = checked and clean. */
  issues?: SpellIssue[]
  ignored?: number
  /** Checked, then edited: the result is out of date. */
  staleCheck?: boolean
  /** This paragraph is being checked / any check is running (buttons wait). */
  checking?: boolean
  checkDisabled?: boolean
  checkError?: unknown
  onCheck?: () => void
  onApplyIssue?: (index: number) => void
  onApplyAll?: () => void
  onIgnoreIssue?: (index: number) => void
  saving: boolean
  onChange: (text: string) => void
  onSave: () => void
}

/** One editable block: textarea, select-text AI actions with an accept/dismiss suggestion, Save. */
export function BlockEditor({
  letterId,
  block,
  value,
  ideas = [],
  issues,
  ignored,
  staleCheck = false,
  checking = false,
  checkDisabled = false,
  checkError,
  onCheck,
  onApplyIssue,
  onApplyAll,
  onIgnoreIssue,
  saving,
  onChange,
  onSave,
}: Props) {
  const t = useT()
  const assist = useAssist(letterId)
  const textarea = useRef<HTMLTextAreaElement>(null)
  // A selection and an AI suggestion carry offsets into the text they were made on: once the
  // text changes (typing, a spelling correction...) they no longer apply, so they are ignored
  // instead of being spliced into the wrong place.
  const [picked, setPicked] = useState<Range & { base: string }>()
  const [proposed, setProposed] = useState<Range & { text: string; base: string }>()
  const selection = picked?.base === value ? picked : undefined
  const suggestion = proposed?.base === value ? proposed : undefined
  const hasSelection = selection && selection.end > selection.start
  const dirty = value !== block.text

  const reset = () => {
    setPicked(undefined)
    setProposed(undefined)
  }
  const focusText = (caret: number) => {
    textarea.current?.focus()
    textarea.current?.setSelectionRange(caret, caret)
  }

  return (
    <div className="space-y-1">
      <Label htmlFor={block.key}>{block.label}</Label>
      {ideas.length > 0 && (
        <div className="rounded-md border border-dashed bg-muted/40 p-2 text-sm">
          <p className="font-medium">{t('letters.editor.ideas')}</p>
          <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
            {ideas.map((idea) => (
              <li key={idea}>{idea}</li>
            ))}
          </ul>
        </div>
      )}
      <Textarea
        id={block.key}
        ref={textarea}
        rows={block.block === 'body' || block.block === 'opening' ? 5 : 2}
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          reset()
        }}
        onSelect={(e) =>
          setPicked({
            start: e.currentTarget.selectionStart,
            end: e.currentTarget.selectionEnd,
            base: e.currentTarget.value,
          })
        }
      />
      {hasSelection && (
        <div
          role="group"
          aria-label={t('letters.editor.ai_actions', { label: block.label })}
          className="flex flex-wrap gap-2"
        >
          {ACTIONS.map((action) => (
            <Button
              key={action}
              size="sm"
              variant="outline"
              loading={assist.isPending && assist.variables?.action === action}
              disabled={assist.isPending}
              onClick={() =>
                assist.mutate(
                  {
                    block: block.block,
                    selection: value.slice(selection.start, selection.end),
                    action,
                  },
                  {
                    onSuccess: (r) =>
                      setProposed({ ...selection, text: r.suggestion, base: value }),
                  },
                )
              }
            >
              {t(`letters.action.${action}`)}
            </Button>
          ))}
        </div>
      )}
      {assist.isPending && (
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner className="size-3.5" /> {t('letters.editor.rewriting')}
        </p>
      )}
      {assist.isError && hasSelection && <ErrorMessage error={assist.error} />}
      {suggestion && (
        <div className="space-y-2 rounded-md border border-primary/50 p-2 text-sm">
          <p className="font-medium">{t('letters.editor.suggestion')}</p>
          <p>{suggestion.text}</p>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => {
                onChange(
                  value.slice(0, suggestion.start) + suggestion.text + value.slice(suggestion.end),
                )
                reset()
              }}
            >
              {t('letters.editor.use')}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setProposed(undefined)}>
              {t('letters.editor.dismiss')}
            </Button>
          </div>
        </div>
      )}
      {onCheck && (
        <SpellPanel
          label={block.label}
          value={value}
          issues={issues}
          ignored={ignored}
          stale={staleCheck}
          unsaved={dirty}
          onApplyIssue={(i) => onApplyIssue?.(i)}
          onApplyAll={() => onApplyAll?.()}
          onIgnoreIssue={(i) => onIgnoreIssue?.(i)}
          onFocusText={focusText}
        />
      )}
      {checkError !== undefined && checkError !== null && <ErrorMessage error={checkError} />}
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={!dirty || saving}
          aria-label={t('letters.editor.save_aria', { label: block.label })}
          onClick={onSave}
        >
          {t('letters.editor.save')}
        </Button>
        {onCheck && (
          <Button
            size="sm"
            variant="outline"
            disabled={checking || checkDisabled || !value.trim()}
            aria-busy={checking}
            aria-label={t('letters.editor.check_aria', { label: block.label })}
            onClick={onCheck}
          >
            {checking ? t('letters.editor.checking') : t('letters.editor.check')}
          </Button>
        )}
      </div>
    </div>
  )
}
