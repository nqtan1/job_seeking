import { FileText, GraduationCap } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { useI18n, useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { StatusBadge } from '@/components/StatusBadge'
import { Button, buttonVariants } from '@/components/ui/button'
import { ApplyLink } from '@/features/pipeline/ApplyLink'
import { useDeleteApplication, useEvents, type Application } from './api'
import { ApplicationForm } from './ApplicationForm'
import { STATUS_KEY, TONE, appName } from './constants'
import { DocumentsDrawer } from './DocumentsDrawer'
import { Drawer } from './Drawer'

function Timeline({ id }: { id: string }) {
  const { t, locale } = useI18n()
  const events = useEvents(id, true)
  if (events.isPending)
    return <p className="text-xs text-muted-foreground">{t('tracker.drawer.timeline_loading')}</p>
  if (events.isError) return <ErrorMessage error={events.error} />
  return (
    <ol
      className="space-y-1 border-l pl-3 text-xs text-muted-foreground"
      aria-label={t('tracker.drawer.timeline')}
    >
      {events.data.map((e) => (
        <li key={e.id}>
          {e.from_status ? `${t(STATUS_KEY[e.from_status])} → ` : ''}
          <strong>{t(STATUS_KEY[e.to_status])}</strong> ·{' '}
          {new Date(e.at).toLocaleDateString(locale)}
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
  const t = useT()
  const del = useDeleteApplication()
  const [showDocs, setShowDocs] = useState(false)
  const [showTimeline, setShowTimeline] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const name = appName(app)
  return (
    <>
      <Drawer
        label={t('tracker.drawer.details_for', { name })}
        title={app.company_name}
        subtitle={[app.job_title, app.location].filter(Boolean).join(' · ') || undefined}
        paused={showDocs}
        onClose={onClose}
      >
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={TONE[app.status]}>{t(STATUS_KEY[app.status])}</StatusBadge>
          <ApplyLink jobId={app.job_id} />
          <Link
            to={`/tracker/${app.id}/prep`}
            className={buttonVariants({ size: 'sm', variant: 'outline' })}
          >
            <GraduationCap /> {t('tracker.drawer.prep')}
          </Link>
          <Button
            size="sm"
            variant="outline"
            aria-haspopup="dialog"
            onClick={() => setShowDocs(true)}
          >
            <FileText /> {t('tracker.drawer.documents')}
          </Button>
        </div>
        <Section title={t('tracker.drawer.details')}>
          <ApplicationForm app={app} onDone={onClose} />
        </Section>
        <Section title={t('tracker.drawer.history')}>
          <Button
            size="sm"
            variant="outline"
            aria-expanded={showTimeline}
            onClick={() => setShowTimeline(!showTimeline)}
          >
            {t('tracker.drawer.timeline')}
          </Button>
          {showTimeline && <Timeline id={app.id} />}
        </Section>
        <Section title={t('tracker.drawer.danger')}>
          {confirming ? (
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="destructive"
                disabled={del.isPending}
                onClick={() => del.mutate(app.id, { onSuccess: onClose })}
              >
                {t('tracker.drawer.confirm_delete')}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setConfirming(false)}>
                {t('tracker.drawer.keep')}
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              aria-label={t('tracker.drawer.delete_aria', { name })}
              onClick={() => setConfirming(true)}
            >
              {t('tracker.drawer.delete')}
            </Button>
          )}
          {del.isError && <ErrorMessage error={del.error} />}
        </Section>
      </Drawer>
      {showDocs && <DocumentsDrawer app={app} name={name} onClose={() => setShowDocs(false)} />}
    </>
  )
}
