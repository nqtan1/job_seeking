import { Check, ChevronRight, Copy, type LucideIcon } from 'lucide-react'
import { type ReactNode, type RefObject, useEffect, useState } from 'react'
import { cn } from 'cn'
import { Link, useBlocker } from 'react-router'
import { useT } from '@/i18n'
import { LIFT } from './lib'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/ui/native-select'
import { useJobs } from '@/features/job-search/api'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/components/StatusBadge'
import type { RunSummary } from './api'
import { Modal } from '@/components/Modal'

/** A selectable card that is still a real checkbox or radio (visually hidden, keyboard focus kept). */
export function ChoiceCard({
  type,
  name,
  checked,
  onChange,
  icon: Icon,
  title,
  hint,
}: {
  type: 'checkbox' | 'radio'
  name?: string
  checked: boolean
  onChange: (checked: boolean) => void
  icon?: LucideIcon
  title: string
  hint?: string
}) {
  return (
    <label
      className={cn(
        'group relative flex cursor-pointer items-start gap-3 rounded-xl border bg-background p-3 transition-colors hover:bg-muted/60',
        'has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50',
        checked && 'border-primary bg-accent/50 hover:bg-accent/60',
      )}
    >
      <input
        type={type}
        name={name}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="peer sr-only"
      />
      {Icon && (
        <Icon
          aria-hidden
          className={cn('mt-0.5 size-4 shrink-0 text-muted-foreground', checked && 'text-primary')}
        />
      )}
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium">{title}</span>
        {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
      </span>
      <span
        aria-hidden
        className={cn(
          'mt-0.5 grid size-4 shrink-0 place-items-center border bg-background',
          type === 'radio' ? 'rounded-full' : 'rounded',
          checked && 'border-primary bg-primary',
        )}
      >
        {checked && <span className="size-1.5 rounded-full bg-primary-foreground" />}
      </span>
    </label>
  )
}

/** A helper or a flow in the gallery: the whole card opens it (stretched link), the quiet
 *  archive action sits above the link. `lead` is the avatar or icon, `children` the detail line. */
export function ItemCard({
  title,
  lead,
  footer,
  children,
}: {
  title: string
  lead: ReactNode
  footer: ReactNode
  children?: ReactNode
}) {
  return (
    <li className={cn('flex flex-col gap-4 rounded-2xl border bg-card p-4 shadow-xs', LIFT)}>
      <div className="flex items-start gap-3">
        {lead}
        <div className="min-w-0 space-y-1">
          <h3 className="truncate font-semibold">{title}</h3>
          {children}
        </div>
      </div>
      <div className="mt-auto flex flex-wrap items-center gap-2 border-t pt-3 text-xs text-muted-foreground">
        {footer}
      </div>
    </li>
  )
}

/** "Pick a job" for helpers that read one (Try it, Run flow). */
const JOB_LABEL_CHARS = 60 // a native list is as wide as its longest line: keep it inside the window

const shorten = (text: string, max: number) =>
  text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`

export function JobSelect({
  id,
  value,
  onChange,
}: {
  id: string
  value: string
  onChange: (jobId: string) => void
}) {
  const t = useT()
  const jobs = useJobs()
  const full = (j: { data: { title: string; company: { name: string } } }) =>
    `${j.data.title} · ${j.data.company.name}`
  const chosen = (jobs.data ?? []).find((j) => j.id === value)
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{t('helpers.pick_job')}</Label>
      <NativeSelect
        id={id}
        className="w-full"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{t('helpers.pick_job_none')}</option>
        {(jobs.data ?? []).map((j) => (
          <option key={j.id} value={j.id} title={full(j)}>
            {shorten(full(j), JOB_LABEL_CHARS)}
          </option>
        ))}
      </NativeSelect>
      {chosen && <p className="text-xs break-words text-muted-foreground">{full(chosen)}</p>}
      {jobs.data?.length === 0 && (
        <p className="text-xs text-muted-foreground">
          {t('helpers.pick_job_empty')}{' '}
          <Link to="/jobs" className="underline">
            {t('helpers.pick_job_add')}
          </Link>
        </p>
      )}
    </div>
  )
}

/** A helper's or step's output: text as written, fields as a small table, with a JSON toggle. */
const FOLD_CHARS = 400 // longer text, or more than 6 lines, folds behind "Show more"
const FOLD_LINES = 6
const LIST_ITEMS = 5

/** `job_title` → "Job title": field names read as labels, not code. */
const label = (k: string) => (k.charAt(0).toUpperCase() + k.slice(1)).replaceAll('_', ' ')

/** A value short enough for a tile (one line, no list): the rest gets the full width. */
const isShort = (v: unknown) =>
  typeof v === 'number' ||
  typeof v === 'boolean' ||
  (typeof v === 'string' && v.length <= 80 && !v.includes('\n'))

/**
 * A step's data as blocks, one per field (like a trace viewer's Input / Output panes): short values
 * sit side by side as tiles, long text folds, lists show their first items, nested records read as
 * label/value pairs. Copy and a raw JSON view stay one click away. With `title`, the blocks come in
 * a card with a header band (the answer of a run).
 */
export function Result({
  value,
  bare,
  large,
  title,
}: {
  value: Record<string, unknown> | null | undefined
  /** No Copy/JSON toolbar (a quiet read-only view, e.g. inside a trace panel). */
  bare?: boolean
  /** Reading size, for the answer the person came for. */
  large?: boolean
  /** A header band above the blocks: the title on the left, Copy/JSON on the right. */
  title?: ReactNode
}) {
  const t = useT()
  const [raw, setRaw] = useState(false)
  const [copied, setCopied] = useState(false)
  if (!value) return null
  const keys = Object.keys(value).filter((k) => !k.startsWith('_') && k !== 'branch')
  // one written answer (a text result, or a single text field) reads as plain text
  const onlyText = keys.length === 1 && typeof value[keys[0]] === 'string'
  const json = JSON.stringify(value, null, 2)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(onlyText ? (value[keys[0]] as string) : json)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard may be blocked: the text stays selectable */
    }
  }
  const tools = !bare && (
    <div className={cn('flex justify-end gap-1', large && !title && '-mt-9')}>
      {!onlyText && (
        <Button variant="ghost" size="xs" onClick={() => setRaw((r) => !r)} aria-pressed={raw}>
          JSON
        </Button>
      )}
      <Button variant="ghost" size="xs" onClick={copy}>
        {copied ? <Check data-icon="inline-start" /> : <Copy data-icon="inline-start" />}
        {copied ? t('helpers.copied') : t('helpers.copy')}
      </Button>
    </div>
  )
  const body = raw ? (
    <pre className="max-h-96 overflow-auto rounded-lg bg-muted p-3 font-mono text-xs">{json}</pre>
  ) : onlyText ? (
    <Folded text={value[keys[0]] as string} large={large} />
  ) : (
    <div className="grid gap-2 sm:grid-cols-2">
      {keys.map((k) => (
        <Field key={k} name={k} v={value[k]} large={large} />
      ))}
    </div>
  )
  if (title)
    return (
      <div className="overflow-hidden rounded-2xl border bg-card shadow-sm">
        <div className="flex items-center gap-3 border-b bg-linear-to-r from-primary/10 via-accent/50 to-transparent px-4 py-3 sm:px-5">
          <div className="min-w-0 flex-1">{title}</div>
          {tools}
        </div>
        <div className="p-4 sm:p-5">{body}</div>
      </div>
    )
  return (
    <div className="space-y-2">
      {tools}
      {body}
    </div>
  )
}

function Field({ name, v, large }: { name: string; v: unknown; large?: boolean }) {
  const short = isShort(v)
  return (
    <div
      className={cn(
        'min-w-0 rounded-xl border bg-background/70 px-3 py-2.5',
        !short && 'sm:col-span-2',
      )}
    >
      <p className="mb-1 text-[0.7rem] font-semibold tracking-wide text-muted-foreground uppercase">
        {label(name)}
      </p>
      <div className={cn('text-sm', short && large && 'text-base font-medium')}>
        <Value v={v} />
      </div>
    </div>
  )
}

function Value({ v }: { v: unknown }) {
  if (Array.isArray(v)) return <List items={v} />
  if (v !== null && typeof v === 'object') return <Pairs record={v as Record<string, unknown>} />
  const text = short(v)
  if (/^https?:\/\/\S+$/.test(text))
    return (
      <a
        href={text}
        target="_blank"
        rel="noreferrer"
        className="break-all text-primary underline-offset-2 hover:underline"
      >
        {text}
      </a>
    )
  return <Folded text={text} />
}

/** Text that folds after a few lines, so a long page or letter never floods the view. */
function Folded({ text, large }: { text: string; large?: boolean }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  if (!text) return <p className="text-sm text-muted-foreground">{t('helpers.ui.nothing')}</p>
  const long = text.length > FOLD_CHARS || text.split('\n').length > FOLD_LINES
  return (
    <div className="space-y-1">
      <p
        className={cn(
          'max-w-prose text-sm leading-relaxed break-words whitespace-pre-wrap',
          large && 'text-base leading-7',
          long && !open && 'line-clamp-6',
        )}
      >
        {text}
      </p>
      {long && (
        <Button variant="link" size="xs" className="px-0" onClick={() => setOpen((o) => !o)}>
          {t(open ? 'helpers.ui.less' : 'helpers.ui.more')}
        </Button>
      )}
    </div>
  )
}

function List({ items }: { items: unknown[] }) {
  const t = useT()
  const [all, setAll] = useState(false)
  if (items.length === 0) return <p className="text-muted-foreground">{t('helpers.ui.nothing')}</p>
  const shown = all ? items : items.slice(0, LIST_ITEMS)
  return (
    <div className="space-y-1.5">
      <ol className="space-y-1.5">
        {shown.map((x, i) => (
          <li key={i} className="flex gap-2.5 rounded-lg bg-muted/50 px-2.5 py-2">
            <span
              aria-hidden
              className="grid size-5 shrink-0 place-items-center rounded-full bg-primary/10 text-[0.7rem] font-semibold text-primary tabular-nums"
            >
              {i + 1}
            </span>
            <div className="min-w-0 flex-1">
              {x !== null && typeof x === 'object' && !Array.isArray(x) ? (
                <Pairs record={x as Record<string, unknown>} />
              ) : (
                <span className="line-clamp-3 break-words">{short(x)}</span>
              )}
            </div>
          </li>
        ))}
      </ol>
      {items.length > LIST_ITEMS && (
        <Button variant="link" size="xs" className="px-0" onClick={() => setAll((a) => !a)}>
          {all ? t('helpers.ui.less') : t('helpers.ui.show_all', { count: items.length })}
        </Button>
      )}
    </div>
  )
}

/** A nested record: one line per field, values cut to a line (the JSON view has the rest). */
function Pairs({ record }: { record: Record<string, unknown> }) {
  const keys = Object.keys(record).filter((k) => !k.startsWith('_'))
  return (
    <dl className="grid grid-cols-[minmax(0,8rem)_1fr] gap-x-3 gap-y-0.5">
      {keys.map((k) => (
        <div key={k} className="contents">
          <dt className="truncate text-xs text-muted-foreground">{label(k)}</dt>
          <dd className="truncate" title={short(record[k])}>
            {short(record[k])}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function short(v: unknown): string {
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (v !== null && typeof v === 'object') return JSON.stringify(v)
  return v == null ? '' : String(v)
}

const TONE = {
  queued: 'neutral',
  running: 'info',
  done: 'success',
  failed: 'danger',
  cancelled: 'warning',
  waiting: 'neutral',
} as const

type Status = RunSummary['status']

export function RunStatusBadge({ status }: { status: Status }) {
  const t = useT()
  return <StatusBadge tone={TONE[status]}>{t(`helpers.run.status.${status}`)}</StatusBadge>
}

/** Shown when a save was refused because someone (or another tab) saved first. */
export function ConflictBanner({ onReload, onKeep }: { onReload: () => void; onKeep: () => void }) {
  const t = useT()
  return (
    <div
      role="alert"
      className="space-y-2 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm"
    >
      <p>{t('helpers.conflict')}</p>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={onReload}>
          {t('helpers.conflict.reload')}
        </Button>
        <Button size="sm" onClick={onKeep}>
          {t('helpers.conflict.keep')}
        </Button>
      </div>
    </div>
  )
}

/** Unsaved-work protection shared by the helper and flow editors: the browser asks before closing
 *  the tab, and leaving the page inside the app asks in a dialog. `leaving` is raised just before
 *  a deliberate reload (the user chose to drop their edits), which must not ask again. */
export function LeaveGuard({ dirty, leaving }: { dirty: boolean; leaving: RefObject<boolean> }) {
  const t = useT()
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => {
      if (!leaving.current) e.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, leaving])
  const blocker = useBlocker(dirty)
  return (
    <Modal open={blocker.state === 'blocked'} label={t('helpers.leave.title')}>
      <h2 className="font-semibold">{t('helpers.leave.title')}</h2>
      <p className="mt-2 text-sm text-muted-foreground">{t('helpers.leave.body')}</p>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="outline" onClick={() => blocker.reset?.()}>
          {t('helpers.leave.stay')}
        </Button>
        <Button variant="destructive" onClick={() => blocker.proceed?.()}>
          {t('helpers.leave.go')}
        </Button>
      </div>
    </Modal>
  )
}

/** One quiet "Details" fold (native <details>): the technical rest, closed unless asked. */
export function Details({
  defaultOpen = false,
  children,
}: {
  defaultOpen?: boolean
  children: ReactNode
}) {
  const t = useT()
  const [open] = useState(defaultOpen) // fixed at mount: a re-render never re-folds what was opened
  return (
    <details open={open} className="group space-y-3">
      <summary className="flex w-fit cursor-pointer list-none items-center gap-1 rounded-lg py-1 pr-2 text-sm font-medium text-muted-foreground outline-none select-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden className="size-4 transition-transform group-open:rotate-90" />
        {t('helpers.ui.details')}
      </summary>
      {children}
    </details>
  )
}
