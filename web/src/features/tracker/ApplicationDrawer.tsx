import { FileText, GraduationCap } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { ErrorMessage } from '@/components/ErrorMessage'
import { StatusBadge } from '@/components/StatusBadge'
import { Button, buttonVariants } from '@/components/ui/button'
import { ApplyLink } from '@/features/pipeline/ApplyLink'
import { useDeleteApplication, useEvents, type Application } from './api'
import { ApplicationForm } from './ApplicationForm'
import { LABEL, TONE, appName } from './constants'
import { DocumentsDrawer } from './DocumentsDrawer'
import { Drawer } from './Drawer'

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

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="space-y-2">
    <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</h3>
    {children}
  </section>
)

/** Everything about one application that does not belong on the card. */
export function ApplicationDrawer({ app, onClose }: { app: Application; onClose: () => void }) {
  const del = useDeleteApplication()
  const [showDocs, setShowDocs] = useState(false)
  const [showTimeline, setShowTimeline] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const name = appName(app)
  return (
    <>
      <Drawer
        label={`Details for ${name}`}
        title={app.company_name}
        subtitle={[app.job_title, app.location].filter(Boolean).join(' · ') || undefined}
        paused={showDocs}
        onClose={onClose}
      >
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={TONE[app.status]}>{LABEL[app.status]}</StatusBadge>
          <ApplyLink jobId={app.job_id} />
          <Link
            to={`/tracker/${app.id}/prep`}
            className={buttonVariants({ size: 'sm', variant: 'outline' })}
          >
            <GraduationCap /> Interview prep
          </Link>
          <Button
            size="sm"
            variant="outline"
            aria-haspopup="dialog"
            onClick={() => setShowDocs(true)}
          >
            <FileText /> Documents
          </Button>
        </div>
        <Section title="Details">
          <ApplicationForm app={app} onDone={onClose} />
        </Section>
        <Section title="History">
          <Button
            size="sm"
            variant="outline"
            aria-expanded={showTimeline}
            onClick={() => setShowTimeline(!showTimeline)}
          >
            Timeline
          </Button>
          {showTimeline && <Timeline id={app.id} />}
        </Section>
        <Section title="Danger zone">
          {confirming ? (
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="destructive"
                disabled={del.isPending}
                onClick={() => del.mutate(app.id, { onSuccess: onClose })}
              >
                Confirm delete
              </Button>
              <Button size="sm" variant="outline" onClick={() => setConfirming(false)}>
                Keep
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              aria-label={`Delete ${name}`}
              onClick={() => setConfirming(true)}
            >
              Delete application
            </Button>
          )}
          {del.isError && <ErrorMessage error={del.error} />}
        </Section>
      </Drawer>
      {showDocs && <DocumentsDrawer app={app} name={name} onClose={() => setShowDocs(false)} />}
    </>
  )
}
