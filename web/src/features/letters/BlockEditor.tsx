import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useAssist, type AssistAction } from './api'
import type { EditorBlock } from './blocks'

const ACTIONS: [AssistAction, string][] = [
  ['shorten', 'Shorten'],
  ['more_formal', 'More formal'],
  ['more_concrete', 'More concrete'],
  ['add_metric', 'Add a metric'],
  ['fix_grammar', 'Fix grammar'],
]

type Range = { start: number; end: number }

type Props = {
  letterId: string
  block: EditorBlock
  /** Current text: the unsaved draft if there is one, else the stored text. */
  value: string
  saving: boolean
  onChange: (text: string) => void
  onSave: () => void
}

/** One editable block: textarea, select-text AI actions with an accept/dismiss suggestion, Save. */
export function BlockEditor({ letterId, block, value, saving, onChange, onSave }: Props) {
  const assist = useAssist(letterId)
  const [selection, setSelection] = useState<Range>()
  const [suggestion, setSuggestion] = useState<Range & { text: string }>()
  const hasSelection = selection && selection.end > selection.start
  const dirty = value !== block.text

  const reset = () => {
    setSelection(undefined)
    setSuggestion(undefined)
  }

  return (
    <div className="space-y-1">
      <Label htmlFor={block.key}>{block.label}</Label>
      <Textarea
        id={block.key}
        rows={block.block === 'body' || block.block === 'opening' ? 5 : 2}
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          reset()
        }}
        onSelect={(e) =>
          setSelection({ start: e.currentTarget.selectionStart, end: e.currentTarget.selectionEnd })
        }
      />
      {hasSelection && (
        <div
          role="group"
          aria-label={`AI actions for ${block.label}`}
          className="flex flex-wrap gap-2"
        >
          {ACTIONS.map(([action, label]) => (
            <Button
              key={action}
              size="sm"
              variant="outline"
              disabled={assist.isPending}
              onClick={() =>
                assist.mutate(
                  {
                    block: block.block,
                    selection: value.slice(selection.start, selection.end),
                    action,
                  },
                  { onSuccess: (r) => setSuggestion({ ...selection, text: r.suggestion }) },
                )
              }
            >
              {label}
            </Button>
          ))}
        </div>
      )}
      {assist.isPending && <p className="text-sm text-muted-foreground">Asking the AI…</p>}
      {assist.isError && hasSelection && <ErrorMessage error={assist.error} />}
      {suggestion && (
        <div className="space-y-2 rounded-md border border-primary/50 p-2 text-sm">
          <p className="font-medium">Suggestion</p>
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
              Use suggestion
            </Button>
            <Button size="sm" variant="outline" onClick={() => setSuggestion(undefined)}>
              Dismiss
            </Button>
          </div>
        </div>
      )}
      <Button
        size="sm"
        variant="outline"
        disabled={!dirty || saving}
        aria-label={`Save ${block.label}`}
        onClick={onSave}
      >
        Save
      </Button>
    </div>
  )
}
