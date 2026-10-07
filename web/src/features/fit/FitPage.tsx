import { Target } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
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

const VERDICT: Record<string, string> = {
  go: 'Strong match',
  maybe: 'Possible match',
  no_go: 'Weak match',
}

function Report({ fit }: { fit: Fit }) {
  const d = fit.data
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-6">
          <ScoreRing score={fit.score} />
          <div className="min-w-0 flex-1 space-y-1">
            <p className="text-lg font-semibold">{VERDICT[d.recommendation] ?? d.recommendation}</p>
            {d.summary && <p className="text-sm text-muted-foreground">{d.summary}</p>}
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <List title="Strengths" items={d.strengths} tone="success" />
        <List title="Gaps" items={d.gaps} tone="warning" />
      </div>
      <List title="Missing requirements" items={d.key_missing_requirements} tone="danger" />
      {d.constructive_feedback && (
        <Card>
          <CardHeader>
            <CardTitle>Advice</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{d.constructive_feedback}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

const STEPS = [
  'Reading your profile and the job…',
  'Comparing skills and requirements…',
  'Writing your report…',
]

export function FitPage() {
  const { jobId = '' } = useParams()
  const job = useJob(jobId)
  const latest = useLatestFit(jobId)
  const run = useRunFit(jobId)
  const [type, setType] = useState<CompanyType>('corporate')

  if (job.isPending || latest.isPending)
    return (
      <Page title="Fit report" back={{ to: '/jobs', label: 'Jobs' }}>
        <ListSkeleton />
      </Page>
    )
  if (job.isError || latest.isError)
    return (
      <Page title="Fit report" back={{ to: '/jobs', label: 'Jobs' }}>
        <ErrorMessage error={job.error ?? latest.error} />
      </Page>
    )

  const fit = run.data ?? latest.data
  return (
    <Page
      title={job.data.data.title}
      description={job.data.data.company.name}
      back={{ to: '/jobs', label: 'Jobs' }}
      actions={
        fit && (
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/letters?job=${jobId}`}
              className={buttonVariants({ variant: 'outline', size: 'sm' })}
            >
              Write a cover letter
            </Link>
            <ApplyActions jobId={jobId} jobSource={job.data.source} />
          </div>
        )
      }
    >
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="company-type">Company type</Label>
            <NativeSelect
              id="company-type"
              value={type}
              onChange={(e) => setType(e.target.value as CompanyType)}
              className="w-fit"
            >
              <NativeSelectOption value="corporate">Corporate</NativeSelectOption>
              <NativeSelectOption value="startup">Startup</NativeSelectOption>
              <NativeSelectOption value="phd">PhD / research</NativeSelectOption>
            </NativeSelect>
          </div>
          <Button disabled={run.isPending} onClick={() => run.mutate(type)}>
            {run.isPending ? 'Analysing…' : fit ? 'Re-run analysis' : 'Analyse my fit'}
          </Button>
        </CardContent>
      </Card>
      {run.isPending && <StepProgress steps={STEPS} />}
      {run.isError && <ErrorMessage error={run.error} />}
      {fit ? (
        <Report fit={fit} />
      ) : (
        <EmptyState
          icon={Target}
          title="No analysis yet"
          description="Run the analysis to see your score, strengths and gaps for this job."
        />
      )}
      <JobDescription job={job.data} />
    </Page>
  )
}
