import { Check, Copy, type LucideIcon } from 'lucide-react'
import { type ReactNode, type RefObject, useEffect, useState } from 'react'
import { cn } from 'cn'
import { Link, useBlocker } from 'react-router'
import { useI18n, useT } from '@/i18n'
import { ConfirmButton } from '@/components/ConfirmButton'
import { LIFT, relTime } from './lib'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/ui/native-select'
import { useJobs } from '@/features/job-search/api'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/components/StatusBadge'
import type { RunSummary } from './api'
import { Modal } from '@/components/Modal'

/** One step of the editor: an icon, a title, one line saying what it is for, then the controls. */
export function SectionCard({
  icon: Icon,
  title,
  help,
  children,
}: {
  icon: LucideIcon
  title: string
  help: string
  children: ReactNode
}) {
  return (
    <section className="rounded-xl border bg-card p-5 shadow-xs">
      <div className="mb-4 flex items-start gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 className="leading-8 font-semibold tracking-tight">{title}</h2>
          <p className="-mt-1 text-sm text-muted-foreground">{help}</p>
        </div>
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  )
}

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
  to,
  title,
  lead,
  version,
  updatedAt,
  archiving,
  onArchive,
  children,
}: {
  to: string
  title: string
  lead: ReactNode
  version: number
  updatedAt: string
  archiving: boolean
  onArchive: (reset: () => void) => void
  children: ReactNode
}) {
  const { t, locale } = useI18n()
  return (
    <li
      className={cn('relative flex flex-col gap-4 rounded-2xl border bg-card p-4 shadow-xs', LIFT)}
    >
      <div className="flex items-start gap-3">
        {lead}
        <div className="min-w-0">
          <Link
            to={to}
            className="block truncate font-semibold outline-none after:absolute after:inset-0 after:rounded-2xl focus-visible:after:ring-3 focus-visible:after:ring-ring/50"
          >
            {title}
          </Link>
          {children}
        </div>
      </div>
      <div className="mt-auto flex items-center gap-2 border-t pt-3 text-xs text-muted-foreground">
        <span className="rounded-full bg-muted px-2 py-0.5 font-medium tabular-nums">
          v{version}
        </span>
        <span className="min-w-0 flex-1 truncate">
          {t('helpers.ui.updated', { when: relTime(updatedAt, locale) })}
        </span>
        <ConfirmButton
          variant="ghost"
          className="relative z-10 text-muted-foreground"
          label={t('helpers.archive')}
          confirmLabel={t('helpers.archive_confirm')}
          cancelLabel={t('helpers.cancel')}
          pending={archiving}
          onConfirm={onArchive}
        />
      </div>
    </li>
  )
}

/** "Pick a job" for helpers that read one (Try it, Run flow). */
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
          <option key={j.id} value={j.id}>
            {j.data.title} · {j.data.company.name}
          </option>
        ))}
      </NativeSelect>
    </div>
  )
}

/** A helper's or step's output: text as written, fields as a small table, with a JSON toggle. */
export function Result({
  value,
  bare,
  large,
}: {
  value: Record<string, unknown> | null | undefined
  /** No Copy/JSON toolbar (a quiet read-only view, e.g. inside a timeline row). */
  bare?: boolean
  /** Reading size, for the answer the person came for. */
  large?: boolean
}) {
  const t = useT()
  const [raw, setRaw] = useState(false)
  const [copied, setCopied] = useState(false)
  if (!value) return null
  const keys = Object.keys(value).filter((k) => !k.startsWith('_') && k !== 'branch')
  // one written answer (a text result, or a single text field) reads as plain text
  const onlyText = keys.length === 1 && typeof value[keys[0]] === 'string'
  const textOf = onlyText ? (value[keys[0]] as string) : ''
  const json = JSON.stringify(value, null, 2)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(onlyText ? textOf : json)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard may be blocked: the text stays selectable */
    }
  }
  return (
    <div className="space-y-2">
      {!bare && (
        <div className={`flex justify-end gap-1${large ? ' -mt-9' : ''}`}>
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
      )}
      {raw ? (
        <pre className="max-h-72 overflow-auto rounded-lg bg-muted p-3 font-mono text-xs">
          {json}
        </pre>
      ) : onlyText ? (
        <p
          className={cn(
            'max-w-prose overflow-auto text-sm leading-relaxed whitespace-pre-wrap',
            large ? 'text-base leading-7' : 'max-h-72 rounded-lg bg-muted/60 p-3',
          )}
        >
          {textOf}
        </p>
      ) : (
        <dl className="divide-y rounded-lg border bg-background/50 text-sm">
          {keys.map((k) => (
            <div key={k} className="grid gap-1 p-2 sm:grid-cols-[10rem_1fr]">
              <dt className="text-xs font-medium text-muted-foreground">{k}</dt>
              <dd className="whitespace-pre-wrap">{display(value[k])}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

function display(v: unknown): string {
  if (Array.isArray(v)) return v.map((x) => `• ${String(x)}`).join('\n')
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
