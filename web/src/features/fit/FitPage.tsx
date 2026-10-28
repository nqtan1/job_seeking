import { Target } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ScoreRing } from '@/components/ScoreRing'
import { ListSkeleton } from '@/components/Skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { StepProgress } from '@/components/StepProgress'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { DeleteJobButton } from '@/features/job-search/DeleteJobButton'
import { useT } from '@/i18n'
import { ApplyActions } from '@/features/pipeline/ApplyActions'
import { JobDescription } from './JobDescription'
import { useJob, useLatestFit, useRunFit, type CompanyType, type Fit } from './api'

const List = ({
  title,
  items,
  tone,
}: {
  title: string
  items: string[]
  tone?: 'success' | 'warning' | 'danger'
}) =>
  items.length > 0 && (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {title} <StatusBadge tone={tone}>{items.length}</StatusBadge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          {items.map((i) => (
            <li key={i}>{i}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )

const VERDICTS = ['go', 'maybe', 'no_go']

function Report({ fit }: { fit: Fit }) {
  const t = useT()
  const d = fit.data
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-6">
          <ScoreRing score={fit.score} />
          <div className="min-w-0 flex-1 space-y-1">
            <p className="text-lg font-semibold">
              {VERDICTS.includes(d.recommendation)
                ? t(`fit.${d.recommendation}` as 'fit.go')
                : d.recommendation}
            </p>
            {d.summary && <p className="text-sm text-muted-foreground">{d.summary}</p>}
            <p className="text-xs text-muted-foreground">{t('fit.disclaimer')}</p>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <List title={t('fit.strengths')} items={d.strengths} tone="success" />
        <List title={t('fit.gaps')} items={d.gaps} tone="warning" />
      </div>
      <List title={t('fit.missing_reqs')} items={d.key_missing_requirements} tone="danger" />
      {d.constructive_feedback && (
        <Card>
          <CardHeader>
            <CardTitle>{t('fit.advice')}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{d.constructive_feedback}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export function FitPage() {
  const t = useT()
  const steps = [t('fit.step_profile'), t('fit.step_compare'), t('fit.step_write')]
  const { jobId = '' } = useParams()
  const job = useJob(jobId)
  const latest = useLatestFit(jobId)
  const run = useRunFit(jobId)
  const [type, setType] = useState<CompanyType>('corporate')
  const navigate = useNavigate()

  if (job.isPending || latest.isPending)
    return (
      <Page title={t('fit.title')} back={{ to: '/jobs', label: t('fit.back') }}>
        <ListSkeleton />
      </Page>
    )
  if (job.isError || latest.isError)
    return (
      <Page title={t('fit.title')} back={{ to: '/jobs', label: t('fit.back') }}>
        <ErrorMessage error={job.error ?? latest.error} />
      </Page>
    )

  const fit = run.data ?? latest.data
  return (
    <Page
      title={job.data.data.title}
      description={job.data.data.company.name?.trim() || t('jobs.company_unset')}
      back={{ to: '/jobs', label: t('fit.back') }}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/?job=${jobId}`}
            className={buttonVariants({ variant: 'outline', size: 'sm' })}
          >
            {t('jobs.discuss')}
          </Link>
          {fit && (
            <>
              <Link
                to={`/letters?job=${jobId}`}
                className={buttonVariants({ variant: 'outline', size: 'sm' })}
              >
                {t('fit.write_letter')}
              </Link>
              <ApplyActions jobId={jobId} jobSource={job.data.source} />
            </>
          )}
        </div>
      }
    >
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="company-type">{t('fit.company_type')}</Label>
            <NativeSelect
              id="company-type"
              value={type}
              onChange={(e) => setType(e.target.value as CompanyType)}
              className="w-fit"
            >
              <NativeSelectOption value="corporate">{t('fit.corporate')}</NativeSelectOption>
              <NativeSelectOption value="startup">{t('fit.startup')}</NativeSelectOption>
              <NativeSelectOption value="phd">{t('fit.phd')}</NativeSelectOption>
            </NativeSelect>
          </div>
          <Button loading={run.isPending} onClick={() => run.mutate(type)}>
            {run.isPending ? t('jobs.analysing') : fit ? t('fit.rerun') : t('fit.analyse')}
          </Button>
        </CardContent>
      </Card>
      {run.isPending && <StepProgress steps={steps} />}
      {run.isError && <ErrorMessage error={run.error} />}
      {fit ? (
        <Report fit={fit} />
      ) : (
        <EmptyState icon={Target} title={t('fit.empty_title')} description={t('fit.empty_desc')} />
      )}
      <JobDescription job={job.data} />
      <Card>
        <CardHeader>
          <CardTitle>{t('fit.delete_title')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">{t('fit.delete_desc')}</p>
          <DeleteJobButton
            id={jobId}
            title={job.data.data.title}
            onDeleted={() => navigate('/jobs')}
          />
        </CardContent>
      </Card>
    </Page>
  )
}
