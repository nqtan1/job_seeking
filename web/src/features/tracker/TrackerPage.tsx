import { Kanban } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  useApplicationDocuments,
  useApplications,
  useAttachDocument,
  useAvailableDocuments,
  useChangeStatus,
  useCreateApplication,
  useDeleteApplication,
  useDetachDocument,
  useUpdateApplication,
  useEvents,
  type Application,
  type ApplicationIn,
  type Status,
} from './api'
import { Link } from 'react-router'
import { cn } from 'cn'
import { ApplyLink } from '@/features/pipeline/ApplyLink'
import { needsAttention } from './attention'

const COLUMNS: [Status, string][] = [
  ['to_apply', 'To apply'],
  ['applied', 'Applied'],
  ['in_review', 'In review'],
  ['interview', 'Interview'],
  ['offer', 'Offer'],
  ['rejected', 'Rejected'],
  ['ghosted', 'Ghosted'],
]
const LABEL = Object.fromEntries(COLUMNS) as Record<Status, string>
const SOURCES = [
  'linkedin',
  'indeed',
  'france_travail',
  'referral',
  'company_site',
  'other',
] as const

function Timeline({ id }: { id: string }) {
  const events = useEvents(id, true)
  if (events.isPending) return <p className="text-xs text-muted-foreground">Loading timeline…</p>
  if (events.isError) return <ErrorMessage error={events.error} />
  return (
    <ol className="space-y-1 border-l pl-3 text-xs text-muted-foreground" aria-label="Timeline">
      {events.data.map((e) => (
        <li key={e.id}>
          {e.from_status ? `${LABEL[e.from_status]} → ` : ''}
          <strong>{LABEL[e.to_status]}</strong> · {new Date(e.at).toLocaleDateString()}
          {e.note ? ` · ${e.note}` : ''}
        </li>
      ))}
    </ol>
  )
}

const KIND_LABEL: Record<string, string> = {
  cv: 'CV',
  letter_pdf: 'Letter (PDF)',
  attachment: 'Attachment',
}
const docName = (d: { kind: string; created_at: string; size: number }) =>
  `${KIND_LABEL[d.kind] ?? d.kind} · ${new Date(d.created_at).toLocaleDateString()} · ${Math.max(1, Math.round(d.size / 1024))} KB`

/** Left-side reader: the files sent with this application, viewable in place (interview prep). */
function DocumentsDrawer({
  app,
  name,
  onClose,
}: {
  app: Application
  name: string
  onClose: () => void
}) {
  const attached = useApplicationDocuments(app.id, true)
  const available = useAvailableDocuments(true)
  const attach = useAttachDocument(app.id)
  const detach = useDetachDocument(app.id)
  const [picked, setPicked] = useState<string>()
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const docs = attached.data ?? []
  const current = docs.find((d) => d.document_id === picked) ?? docs[0]
  const taken = new Set(docs.map((d) => d.document_id))
  const choices = (available.data ?? []).filter((d) => !taken.has(d.document_id))
  return (
    <aside
      role="dialog"
      aria-label={`Documents for ${name}`}
      className="fixed inset-y-0 left-0 z-40 flex w-full max-w-lg flex-col gap-3 border-r bg-background p-4 shadow-xl"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">Documents sent</h2>
          <p className="text-xs text-muted-foreground">{name}</p>
        </div>
        <Button size="sm" variant="outline" onClick={onClose}>
          Close
        </Button>
      </div>
      {attached.isPending && <p className="text-xs text-muted-foreground">Loading documents…</p>}
      {attached.isError && <ErrorMessage error={attached.error} />}
      {attached.data && docs.length === 0 && (
        <p className="text-sm text-muted-foreground">No documents attached yet.</p>
      )}
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Attached documents">
        {docs.map((d) => (
          <Button
            key={d.document_id}
            size="sm"
            role="tab"
            aria-selected={d.document_id === current?.document_id}
            variant={d.document_id === current?.document_id ? 'default' : 'outline'}
            onClick={() => setPicked(d.document_id)}
          >
            {d.filename}
          </Button>
        ))}
      </div>
      {current && (
        <>
          {current.mime.startsWith('image/') ? (
            <img
              src={current.download_url}
              alt={current.filename}
              className="min-h-0 flex-1 rounded-lg border bg-white object-contain"
            />
          ) : (
            <iframe
              title={current.filename}
              src={current.download_url}
              className="min-h-0 flex-1 rounded-lg border bg-white"
            />
          )}
          <div className="flex gap-2">
            <a
              href={current.download_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs underline underline-offset-2"
            >
              Open in new tab
            </a>
            <a
              href={current.save_url}
              className="text-xs underline underline-offset-2"
              aria-label={`Download ${current.filename}`}
            >
              Download
            </a>
            <Button
              size="sm"
              variant="ghost"
              disabled={detach.isPending}
              aria-label={`Remove ${current.filename}`}
              onClick={() =>
                detach.mutate(current.document_id, { onSuccess: () => setPicked(undefined) })
              }
            >
              Remove from this application
            </Button>
          </div>
        </>
      )}
      {choices.length > 0 && (
        <NativeSelect
          aria-label="Attach a document"
          className="w-full"
          value=""
          disabled={attach.isPending}
          onChange={(e) =>
            attach.mutate(e.target.value, { onSuccess: () => setPicked(e.target.value) })
          }
        >
          <NativeSelectOption value="" disabled>
            Attach a document…
          </NativeSelectOption>
          {choices.map((d) => (
            <NativeSelectOption key={d.document_id} value={d.document_id}>
              {docName(d)}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      )}
      {(attach.isError || detach.isError) && <ErrorMessage error={attach.error ?? detach.error} />}
    </aside>
  )
}

/** `<input type="datetime-local">` wants local time without a zone: "2026-10-20T14:00". */
const toLocalInput = (iso: string | null) => {
  if (!iso) return ''
  const d = new Date(iso)
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

/** Notes, the person to contact and the interview date: what the user needs on interview day. */
function Details({ app, onDone }: { app: Application; onDone: () => void }) {
  const update = useUpdateApplication()
  const { register, handleSubmit } = useForm({
    defaultValues: {
      notes: app.notes ?? '',
      contact: app.contact ?? '',
      interview_at: toLocalInput(app.interview_at),
    },
  })
  return (
    <form
      className="space-y-2"
      onSubmit={handleSubmit((v) =>
        update.mutate(
          {
            id: app.id,
            changes: {
              notes: v.notes || null,
              contact: v.contact || null,
              interview_at: v.interview_at ? new Date(v.interview_at).toISOString() : null,
            },
          },
          { onSuccess: onDone },
        ),
      )}
    >
      <Label htmlFor={`contact-${app.id}`}>Contact</Label>
      <Input id={`contact-${app.id}`} placeholder="Name, email or phone" {...register('contact')} />
      <Label htmlFor={`interview-${app.id}`}>Interview</Label>
      <Input id={`interview-${app.id}`} type="datetime-local" {...register('interview_at')} />
      <Label htmlFor={`notes-${app.id}`}>Notes</Label>
      <Input id={`notes-${app.id}`} {...register('notes')} />
      {update.isError && <ErrorMessage error={update.error} />}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={update.isPending}>
          Save
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function ApplicationCard({ app }: { app: Application }) {
  const change = useChangeStatus()
  const del = useDeleteApplication()
  const [showTimeline, setShowTimeline] = useState(false)
  const [showDocs, setShowDocs] = useState(false)
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const name = app.job_title ? `${app.job_title} — ${app.company_name}` : app.company_name
  return (
    <li
      draggable
      onDragStart={(e) => e.dataTransfer.setData('text/plain', app.id)}
      className="cursor-grab space-y-2 rounded-lg border bg-card p-3 text-sm shadow-xs active:cursor-grabbing"
    >
      <p className="font-medium">{name}</p>
      <p className="text-xs text-muted-foreground">{app.source.replace('_', ' ')}</p>
      {app.interview_at && (
        <p className="text-xs font-medium text-primary">
          Interview{' '}
          {new Date(app.interview_at).toLocaleString([], {
            dateStyle: 'medium',
            timeStyle: 'short',
          })}
        </p>
      )}
      {app.contact && <p className="text-xs text-muted-foreground">Contact: {app.contact}</p>}
      {app.notes && <p className="text-xs">{app.notes}</p>}
      {editing && <Details app={app} onDone={() => setEditing(false)} />}
      {app.next_statuses.length > 0 && (
        <NativeSelect
          aria-label={`Move ${name}`}
          className="w-full"
          value=""
          disabled={change.isPending}
          onChange={(e) => change.mutate({ id: app.id, status: e.target.value as Status })}
        >
          <NativeSelectOption value="" disabled>
            Move to…
          </NativeSelectOption>
          {app.next_statuses.map((s) => (
            <NativeSelectOption key={s} value={s}>
              {LABEL[s]}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      )}
      {change.isError && <ErrorMessage error={change.error} />}
      <div className="flex gap-2">
        <ApplyLink jobId={app.job_id} />
        <Button
          size="sm"
          variant="outline"
          aria-expanded={showTimeline}
          onClick={() => setShowTimeline(!showTimeline)}
        >
          Timeline
        </Button>
        <Button
          size="sm"
          variant="outline"
          aria-expanded={editing}
          onClick={() => setEditing(!editing)}
        >
          Details
        </Button>
        <Button
          size="sm"
          variant="outline"
          aria-haspopup="dialog"
          onClick={() => setShowDocs(true)}
        >
          Documents
        </Button>
        {confirming ? (
          <Button
            size="sm"
            variant="destructive"
            disabled={del.isPending}
            onClick={() => del.mutate(app.id)}
          >
            Confirm delete
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            aria-label={`Delete ${name}`}
            onClick={() => setConfirming(true)}
          >
            Delete
          </Button>
        )}
      </div>
      {del.isError && <ErrorMessage error={del.error} />}
      {showTimeline && <Timeline id={app.id} />}
      {showDocs && <DocumentsDrawer app={app} name={name} onClose={() => setShowDocs(false)} />}
    </li>
  )
}

/** "Needs attention": a follow-up to send, or an interview coming up. */
function Attention({ apps }: { apps: Application[] }) {
  const items = needsAttention(apps)
  if (items.length === 0) return null
  return (
    <section
      aria-label="Needs attention"
      className="space-y-2 rounded-xl border border-warning/40 bg-warning/10 p-4"
    >
      <h2 className="text-sm font-semibold">Needs attention</h2>
      <ul className="space-y-2 text-sm">
        {items.map(({ app, kind, days }) => (
          <li
            key={`${kind}-${app.id}`}
            className="flex flex-wrap items-center justify-between gap-2"
          >
            <span>
              {kind === 'interview'
                ? `Interview at ${app.company_name} ${days === 0 ? 'today' : `in ${days} day${days > 1 ? 's' : ''}`}`
                : `${app.company_name}: no reply after ${days} days`}
            </span>
            {kind === 'interview' ? (
              <Link to={`/tracker/${app.id}/prep`} className={buttonVariants({ size: 'sm' })}>
                Prepare
              </Link>
            ) : (
              <Link
                to={`/?ask=${encodeURIComponent(`Help me write a short follow-up email to ${app.company_name}${app.job_title ? ` about the ${app.job_title} role` : ''}. I applied ${days} days ago and have had no reply.`)}`}
                className={buttonVariants({ size: 'sm', variant: 'outline' })}
              >
                Draft a follow-up
              </Link>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function AddForm() {
  const create = useCreateApplication()
  const { register, handleSubmit, reset } = useForm<ApplicationIn>({
    defaultValues: { source: 'other', status: 'to_apply' },
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Track an application</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-3 sm:grid-cols-4"
          onSubmit={handleSubmit((v) =>
            create.mutate(
              { ...v, job_title: v.job_title || null, notes: v.notes || null },
              { onSuccess: () => reset() },
            ),
          )}
        >
          <div className="space-y-1">
            <Label htmlFor="company">Company</Label>
            <Input id="company" {...register('company_name', { required: true })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="title">Job title</Label>
            <Input id="title" {...register('job_title')} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="source">Source</Label>
            <NativeSelect id="source" className="w-full" {...register('source')}>
              {SOURCES.map((s) => (
                <NativeSelectOption key={s} value={s}>
                  {s.replace('_', ' ')}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <div className="space-y-1">
            <Label htmlFor="status">Status</Label>
            <NativeSelect id="status" className="w-full" {...register('status')}>
              <NativeSelectOption value="to_apply">To apply</NativeSelectOption>
              <NativeSelectOption value="applied">Applied</NativeSelectOption>
            </NativeSelect>
          </div>
          <div className="space-y-1 sm:col-span-4">
            <Label htmlFor="notes">Notes</Label>
            <Input id="notes" {...register('notes')} />
          </div>
          {create.isError && <ErrorMessage error={create.error} />}
          <Button type="submit" className="sm:w-fit" disabled={create.isPending}>
            {create.isPending ? 'Adding…' : 'Add application'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

const DOT: Record<Status, string> = {
  to_apply: 'bg-muted-foreground',
  applied: 'bg-primary',
  in_review: 'bg-warning',
  interview: 'bg-chart-2',
  offer: 'bg-success',
  rejected: 'bg-destructive',
  ghosted: 'bg-muted-foreground/50',
}

export function TrackerPage() {
  const apps = useApplications()
  const change = useChangeStatus()
  const [over, setOver] = useState<Status>()
  // Dropping a card on a column is the same call as the "Move to…" select; the server still
  // decides which moves are allowed (`next_statuses`).
  const drop = (status: Status, id: string) => {
    setOver(undefined)
    const app = apps.data?.find((a) => a.id === id)
    if (app && app.status !== status && app.next_statuses.includes(status))
      change.mutate({ id, status })
  }
  return (
    <Page title="Tracker" description="Follow every application from first idea to offer." wide>
      <AddForm />
      {apps.data && <Attention apps={apps.data} />}
      {apps.isPending && <ListSkeleton rows={2} />}
      {apps.isError && <ErrorMessage error={apps.error} />}
      {change.isError && <ErrorMessage error={change.error} />}
      {apps.data?.length === 0 && (
        <EmptyState
          icon={Kanban}
          title="No applications yet"
          description="Add the first one above. Drag cards between columns as things move."
        />
      )}
      {apps.data && apps.data.length > 0 && (
        <div className="grid auto-cols-[16rem] grid-flow-col gap-3 overflow-x-auto pb-2">
          {COLUMNS.map(([status, label]) => {
            const items = apps.data.filter((a) => a.status === status)
            return (
              <section
                key={status}
                aria-label={label}
                onDragOver={(e) => {
                  e.preventDefault()
                  setOver(status)
                }}
                onDragLeave={() => setOver(undefined)}
                onDrop={(e) => drop(status, e.dataTransfer.getData('text/plain'))}
                className={cn(
                  'min-h-40 space-y-2 rounded-xl bg-muted/50 p-2 transition-colors',
                  over === status && 'bg-accent ring-2 ring-primary/40',
                )}
              >
                <h2 className="flex items-center gap-2 px-1 text-sm font-semibold">
                  <span className={cn('size-2 rounded-full', DOT[status])} />
                  {label}
                  <span className="text-muted-foreground">({items.length})</span>
                </h2>
                <ul className="space-y-2">
                  {items.map((a) => (
                    <ApplicationCard key={a.id} app={a} />
                  ))}
                </ul>
              </section>
            )
          })}
        </div>
      )}
    </Page>
  )
}
