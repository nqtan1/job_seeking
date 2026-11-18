import { Pencil, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ErrorMessage } from '@/components/ErrorMessage'
import { ListSkeleton } from '@/components/Skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useT } from '@/i18n'
import type { components } from '@/lib/api/schema'
import { useMemory, useSaveMemory } from './api'

type FactIn = components['schemas']['FactIn']
const MAX_FACTS = 30
const MAX_CHARS = 200
const COUNT_FROM = 160 // the character count shows only near the limit

function FactRow({
  fact,
  busy,
  onSave,
  onDelete,
}: {
  fact: FactIn
  busy: boolean
  onSave: (text: string) => Promise<unknown>
  onDelete: (reset: () => void) => void
}) {
  const t = useT()
  const [draft, setDraft] = useState<string>()
  const editLabel = t('settings.memory.edit_aria', { text: fact.text })
  if (draft !== undefined)
    return (
      <li>
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            // the draft stays open when the save fails (the error shows below the list)
            onSave(draft.trim()).then(
              () => setDraft(undefined),
              () => {},
            )
          }}
        >
          <Input
            aria-label={editLabel}
            value={draft}
            maxLength={MAX_CHARS}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            className="min-w-0 flex-1"
          />
          <Button type="submit" variant="outline" disabled={busy || !draft.trim()}>
            {t('settings.memory.save')}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setDraft(undefined)}>
            {t('settings.memory.cancel')}
          </Button>
        </form>
      </li>
    )
  return (
    <li className="flex items-start gap-2">
      <span className="min-w-0 flex-1 py-1 break-words">{fact.text}</span>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={editLabel}
        disabled={busy}
        onClick={() => setDraft(fact.text)}
      >
        <Pencil />
      </Button>
      <ConfirmButton
        variant="ghost"
        label={<Trash2 aria-hidden />}
        aria-label={t('ui.remove', { name: fact.text })}
        confirmLabel={t('settings.memory.delete')}
        confirmAriaLabel={`${t('settings.memory.delete')}: ${fact.text}`}
        cancelLabel={t('settings.memory.cancel')}
        pending={busy}
        disabled={busy}
        onConfirm={onDelete}
      />
    </li>
  )
}

function AddFact({
  disabled,
  onAdd,
}: {
  disabled: boolean
  onAdd: (text: string) => Promise<unknown>
}) {
  const t = useT()
  const [text, setText] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    onAdd(text.trim()).then(
      () => setText(''),
      () => {},
    ) // kept on failure
  }
  const counted = text.length > COUNT_FROM
  return (
    <form onSubmit={submit} className="space-y-1">
      <Label htmlFor="memory-new">{t('settings.memory.add_label')}</Label>
      <div className="flex flex-wrap gap-2">
        <Input
          id="memory-new"
          value={text}
          maxLength={MAX_CHARS}
          disabled={disabled}
          aria-describedby={counted ? 'memory-count' : undefined}
          onChange={(e) => setText(e.target.value)}
          className="min-w-0 flex-1"
        />
        <Button type="submit" disabled={disabled || !text.trim()}>
          {t('settings.memory.add')}
        </Button>
      </div>
      {counted && (
        <p id="memory-count" className="text-xs text-muted-foreground tabular-nums">
          {text.length}/{MAX_CHARS}
        </p>
      )}
    </form>
  )
}

/** What the assistant remembers about the user: theirs to read, fix and delete. */
export function MemoryCard() {
  const t = useT()
  const memory = useMemory()
  const save = useSaveMemory()
  const facts: FactIn[] = memory.data?.facts ?? []
  const put = (next: FactIn[]) => save.mutateAsync(next)
  return (
    <Card id="memory">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {t('settings.memory.title')}
          {memory.isSuccess && (
            <StatusBadge>
              {facts.length}/{MAX_FACTS}
            </StatusBadge>
          )}
        </CardTitle>
        <CardDescription>{t('settings.memory.desc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {memory.isPending && <ListSkeleton rows={2} />}
        {memory.isError && <ErrorMessage error={memory.error} />}
        {memory.isSuccess && facts.length === 0 && (
          <p className="text-muted-foreground">{t('settings.memory.empty')}</p>
        )}
        <ul className="space-y-1">
          {facts.map((f, i) => (
            <FactRow
              key={f.id ?? i}
              fact={f}
              busy={save.isPending}
              onSave={(text) => put(facts.map((x, j) => (j === i ? { ...x, text } : x)))}
              onDelete={(reset) => put(facts.filter((_, j) => j !== i)).then(reset, reset)}
            />
          ))}
        </ul>
        {save.isError && <ErrorMessage error={save.error} />}
        <AddFact
          disabled={!memory.isSuccess || save.isPending || facts.length >= MAX_FACTS}
          onAdd={(text) => put([...facts, { text }])}
        />
      </CardContent>
    </Card>
  )
}
