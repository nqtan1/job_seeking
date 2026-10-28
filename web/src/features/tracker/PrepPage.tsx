import { Link, useParams } from 'react-router'
import { useI18n, useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { StepProgress } from '@/components/StepProgress'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useJob, useLatestFit } from '@/features/fit/api'
import { useApplicationDocuments, useApplications, useInterviewPrep } from './api'
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
  const t = useT()
  const job = useJob(jobId)
  const fit = useLatestFit(jobId)
  const d = job.data?.data
  return (
    <>
      {d && d.missions.length > 0 && (
        <Section title={t('tracker.prep.role')}>
          <Bullets items={d.missions} />
        </Section>
      )}
      {fit.data && (
        <Section title={t('tracker.prep.strong')}>
          <p className="text-sm font-medium">{t('tracker.prep.strengths')}</p>
          <Bullets items={fit.data.data.strengths} />
          <p className="text-sm font-medium">{t('tracker.prep.gaps')}</p>
          <Bullets items={[...fit.data.data.gaps, ...fit.data.data.key_missing_requirements]} />
          {fit.data.data.constructive_feedback && (
            <p className="text-sm text-muted-foreground">{fit.data.data.constructive_feedback}</p>
          )}
        </Section>
      )}
    </>
  )
}

function Questions({ id }: { id: string }) {
  const t = useT()
  const prep = useInterviewPrep(id)
  return (
    <Section title={t('tracker.prep.questions')}>
      {!prep.data && (
        <>
          <p className="text-sm text-muted-foreground">{t('tracker.prep.questions_intro')}</p>
          <Button size="sm" disabled={prep.isPending} onClick={() => prep.mutate()}>
            {prep.isPending ? t('tracker.prep.preparing') : t('tracker.prep.prepare')}
          </Button>
        </>
      )}
      {prep.isPending && <StepProgress steps={[t('tracker.prep.reading')]} />}
      {prep.isError && <ErrorMessage error={prep.error} />}
      <ol className="space-y-4">
        {prep.data?.questions.map((q) => (
          <li key={q.question} className="space-y-1">
            <p className="text-sm font-medium">{q.question}</p>
            <p className="text-xs text-muted-foreground">{q.why_asked}</p>
            <Bullets items={q.answer_outline} />
            {q.from_profile && (
              <p className="text-xs text-muted-foreground">
                {t('tracker.prep.from_profile', { text: q.from_profile })}
              </p>
            )}
          </li>
        ))}
      </ol>
      {prep.data && <p className="text-xs text-muted-foreground">{t('tracker.prep.ai_note')}</p>}
    </Section>
  )
}

function Sent({ id }: { id: string }) {
  const t = useT()
  const docs = useApplicationDocuments(id, true)
  if (docs.isPending)
    return <p className="text-sm text-muted-foreground">{t('tracker.prep.loading')}</p>
  if (docs.isError) return <ErrorMessage error={docs.error} />
  if (docs.data.length === 0)
    return <p className="text-sm text-muted-foreground">{t('tracker.prep.nothing_sent')}</p>
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
  const { t, locale } = useI18n()
  const { applicationId = '' } = useParams()
  const apps = useApplications()
  const app = apps.data?.find((a) => a.id === applicationId)
  const back = { to: '/tracker', label: t('tracker.proof.back') }
  if (apps.isPending)
    return (
      <Page title={t('tracker.prep.title')} back={back}>
        <ListSkeleton />
      </Page>
    )
  if (apps.isError || !app)
    return (
      <Page title={t('tracker.prep.title')} back={back}>
        {apps.isError ? <ErrorMessage error={apps.error} /> : <p>{t('tracker.prep.not_found')}</p>}
      </Page>
    )
  return (
    <Page
      title={app.job_title ? `${app.job_title} — ${app.company_name}` : app.company_name}
      description={
        app.interview_at
          ? t('tracker.prep.interview_at', {
              date: new Date(app.interview_at).toLocaleString(locale, {
                dateStyle: 'full',
                timeStyle: 'short',
              }),
            })
          : t('tracker.prep.no_date')
      }
      back={back}
      actions={
        <Link
          to={`/?${app.job_id ? `job=${app.job_id}&` : ''}ask=${encodeURIComponent(practicePrompt(app, t))}`}
          className={buttonVariants({ size: 'sm' })}
        >
          {t('tracker.prep.practise')}
        </Link>
      }
    >
      {(app.contact || app.notes) && (
        <Section title={t('tracker.prep.notes')}>
          {app.contact && (
            <p className="text-sm">{t('tracker.prep.contact', { contact: app.contact })}</p>
          )}
          {app.notes && <p className="text-sm text-muted-foreground">{app.notes}</p>}
        </Section>
      )}
      {app.job_id && <JobSections jobId={app.job_id} />}
      {app.job_id && <Questions id={app.id} />}
      <Section title={t('tracker.prep.sent')}>
        <Sent id={app.id} />
      </Section>
    </Page>
  )
}
