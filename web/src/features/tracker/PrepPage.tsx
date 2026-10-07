import { Link, useParams } from 'react-router'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useJob, useLatestFit } from '@/features/fit/api'
import { useApplicationDocuments, useApplications } from './api'
import { practicePrompt } from './attention'

const Bullets = ({ items }: { items: string[] }) => (
  <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
    {items.map((i) => (
      <li key={i}>{i}</li>
    ))}
  </ul>
)

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <Card>
    <CardHeader>
      <CardTitle>{title}</CardTitle>
    </CardHeader>
    <CardContent className="space-y-2">{children}</CardContent>
  </Card>
)

function JobSections({ jobId }: { jobId: string }) {
  const job = useJob(jobId)
  const fit = useLatestFit(jobId)
  const d = job.data?.data
  return (
    <>
      {d && d.missions.length > 0 && (
        <Section title="The role">
          <Bullets items={d.missions} />
        </Section>
      )}
      {fit.data && (
        <Section title="Where you are strong, and where to prepare">
          <p className="text-sm font-medium">Strengths</p>
          <Bullets items={fit.data.data.strengths} />
          <p className="text-sm font-medium">Gaps to be ready for</p>
          <Bullets items={[...fit.data.data.gaps, ...fit.data.data.key_missing_requirements]} />
          {fit.data.data.constructive_feedback && (
            <p className="text-sm text-muted-foreground">{fit.data.data.constructive_feedback}</p>
          )}
        </Section>
      )}
    </>
  )
}

function Sent({ id }: { id: string }) {
  const docs = useApplicationDocuments(id, true)
  if (docs.isPending) return <p className="text-sm text-muted-foreground">Loading…</p>
  if (docs.isError) return <ErrorMessage error={docs.error} />
  if (docs.data.length === 0)
    return (
      <p className="text-sm text-muted-foreground">Nothing attached to this application yet.</p>
    )
  return (
    <ul className="space-y-1 text-sm">
      {docs.data.map((d) => (
        <li key={d.document_id}>
          <a
            href={d.download_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline underline-offset-2"
          >
            {d.filename}
          </a>
        </li>
      ))}
    </ul>
  )
}

/** Everything for interview day on one page: the role, where to prepare, what was sent. */
export function PrepPage() {
  const { applicationId = '' } = useParams()
  const apps = useApplications()
  const app = apps.data?.find((a) => a.id === applicationId)
  const back = { to: '/tracker', label: 'Tracker' }
  if (apps.isPending)
    return (
      <Page title="Interview prep" back={back}>
        <ListSkeleton />
      </Page>
    )
  if (apps.isError || !app)
    return (
      <Page title="Interview prep" back={back}>
        {apps.isError ? <ErrorMessage error={apps.error} /> : <p>Application not found.</p>}
      </Page>
    )
  return (
    <Page
      title={app.job_title ? `${app.job_title} — ${app.company_name}` : app.company_name}
      description={
        app.interview_at
          ? `Interview ${new Date(app.interview_at).toLocaleString([], { dateStyle: 'full', timeStyle: 'short' })}`
          : 'No interview date yet. Add one in the tracker (Details).'
      }
      back={back}
      actions={
        <Link
          to={`/?ask=${encodeURIComponent(practicePrompt(app))}`}
          className={buttonVariants({ size: 'sm' })}
        >
          Practise with the coach
        </Link>
      }
    >
      {(app.contact || app.notes) && (
        <Section title="Your notes">
          {app.contact && <p className="text-sm">Contact: {app.contact}</p>}
          {app.notes && <p className="text-sm text-muted-foreground">{app.notes}</p>}
        </Section>
      )}
      {app.job_id && <JobSections jobId={app.job_id} />}
      <Section title="What you sent">
        <Sent id={app.id} />
      </Section>
    </Page>
  )
}
