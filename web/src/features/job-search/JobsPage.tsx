import { ContractPicker } from '@/components/ContractPicker'
import { PlacePicker } from '@/components/PlacePicker'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { StepProgress } from '@/components/StepProgress'
import { toast } from '@/lib/toast'
import { ApplyActions } from '@/features/pipeline/ApplyActions'
import { usePipeline } from '@/features/pipeline/api'
import { useRadarJobIds } from '@/features/radar/api'
import { Briefcase } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { Controller, useForm } from 'react-hook-form'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useAddJob, useJobs, useSearchJobs, type SearchParams } from './api'

function ManualEntry({ add }: { add: ReturnType<typeof useAddJob> }) {
  const { register, handleSubmit, reset, formState } = useForm<{ text: string }>()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Paste a job description</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-3"
          onSubmit={handleSubmit(({ text }) => add.mutate({ text }, { onSuccess: () => reset() }))}
        >
          <Label htmlFor="jd-text">Job description text</Label>
          <Textarea id="jd-text" rows={6} {...register('text', { required: true })} />
          {formState.errors.text && (
            <p role="alert" className="text-sm text-destructive">
              Paste the job description first.
            </p>
          )}
          <Button type="submit" disabled={add.isPending}>
            {add.isPending ? 'Analysing…' : 'Add job'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function FileEntry({ add }: { add: ReturnType<typeof useAddJob> }) {
  const file = useRef<HTMLInputElement>(null)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload a job description file</CardTitle>
        <CardDescription>PDF, DOCX or image.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Label htmlFor="jd-file">Job description file</Label>
        <Input id="jd-file" type="file" accept=".pdf,.docx,image/*" ref={file} />
        <Button
          disabled={add.isPending}
          onClick={() => {
            const f = file.current?.files?.[0]
            if (f) add.mutate({ file: f })
          }}
        >
          {add.isPending ? 'Analysing…' : 'Upload and add'}
        </Button>
      </CardContent>
    </Card>
  )
}

function Search({ add }: { add: ReturnType<typeof useAddJob> }) {
  const [params, setParams] = useState<SearchParams>()
  const search = useSearchJobs(params)
  const { register, handleSubmit, control } = useForm<SearchParams>()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Search France Travail</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form className="grid gap-3 sm:grid-cols-4" onSubmit={handleSubmit(setParams)}>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="q">Keywords</Label>
            <Input id="q" {...register('query')} />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label>Where</Label>
            <Controller
              control={control}
              name="department"
              render={({ field }) => (
                <PlacePicker value={field.value} onChange={(v) => field.onChange(v ?? undefined)} />
              )}
            />
          </div>
          <div className="space-y-1 sm:col-span-4">
            <Label>Contract types</Label>
            <Controller
              control={control}
              name="contract_type"
              render={({ field }) => (
                <ContractPicker
                  value={field.value}
                  onChange={(v) => field.onChange(v ?? undefined)}
                />
              )}
            />
          </div>
          <Button type="submit" className="sm:col-span-4 sm:w-fit" disabled={search.isFetching}>
            {search.isFetching ? 'Searching…' : 'Search'}
          </Button>
        </form>
        {search.isError && <ErrorMessage error={search.error} />}
        {search.data?.results.length === 0 && (
          <p className="text-sm text-muted-foreground">No offers found.</p>
        )}
        <ul className="space-y-2">
          {search.data?.results.map((r) => (
            <li key={r.id} className="flex items-start justify-between gap-4 rounded-lg border p-3">
              <div>
                <p className="font-medium">{r.title}</p>
                <p className="text-sm text-muted-foreground">
                  {[r.company, r.location, r.contract_type_label].filter(Boolean).join(' · ')}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                disabled={add.isPending}
                aria-label={`Add ${r.title}`}
                onClick={() => add.mutate({ externalId: r.id })}
              >
                Add
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

const VERDICT_TONE = { go: 'success', maybe: 'warning', no_go: 'danger' } as const

function JobList() {
  const jobs = useJobs()
  const pipeline = usePipeline()
  const fromRadar = useRadarJobIds()
  const [bestFirst, setBestFirst] = useState(false)
  if (jobs.isPending) return <ListSkeleton />
  if (jobs.isError) return <ErrorMessage error={jobs.error} />
  if (jobs.data.length === 0)
    return (
      <EmptyState
        icon={Briefcase}
        title="No jobs yet"
        description="Paste a description, upload a file or search offers to add your first job."
      />
    )
  const rows = bestFirst
    ? [...jobs.data].sort(
        (a, b) => (pipeline.fit(b.id)?.score ?? -1) - (pipeline.fit(a.id)?.score ?? -1),
      )
    : jobs.data
  return (
    <div className="space-y-2">
      <Button
        size="sm"
        variant="outline"
        aria-pressed={bestFirst}
        onClick={() => setBestFirst(!bestFirst)}
      >
        {bestFirst ? 'Newest first' : 'Best fit first'}
      </Button>
      <ul className="space-y-2">
        {rows.map((j) => {
          const fit = pipeline.fit(j.id)
          const letters = pipeline.letters(j.id)
          const app = pipeline.application(j.id)
          return (
            <li key={j.id} className="space-y-3 rounded-xl border bg-card p-4 shadow-xs">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 space-y-1">
                  <p className="truncate font-medium">{j.data.title}</p>
                  <p className="truncate text-sm text-muted-foreground">{j.data.company.name}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone="info">{j.source.replace('_', ' ')}</StatusBadge>
                    {fromRadar.has(j.id) && <StatusBadge tone="success">From radar</StatusBadge>}
                    {fit ? (
                      <StatusBadge
                        tone={VERDICT_TONE[fit.data.recommendation as keyof typeof VERDICT_TONE]}
                      >
                        Fit {Math.round(fit.score)}%
                      </StatusBadge>
                    ) : (
                      <StatusBadge>Fit not checked</StatusBadge>
                    )}
                    <StatusBadge tone={letters.length ? 'success' : 'neutral'}>
                      {letters.length
                        ? `${letters.length} letter${letters.length > 1 ? 's' : ''}`
                        : 'No letter'}
                    </StatusBadge>
                    {app && (
                      <StatusBadge tone="success">
                        Tracked: {app.status.replace('_', ' ')}
                      </StatusBadge>
                    )}
                  </div>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {new Date(j.created_at).toLocaleDateString()}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  to={`/jobs/${j.id}/fit`}
                  className={buttonVariants({ variant: fit ? 'outline' : 'default', size: 'sm' })}
                >
                  {fit ? 'Fit report' : 'Check fit'}
                </Link>
                <Link
                  to={letters[0] ? `/letters/${letters[0].id}` : `/letters?job=${j.id}`}
                  className={buttonVariants({ variant: 'outline', size: 'sm' })}
                >
                  {letters[0] ? 'Open letter' : 'Write letter'}
                </Link>
                <ApplyActions
                  jobId={j.id}
                  jobSource={j.source}
                  pdfDocumentId={letters[0]?.pdf_document_id}
                />
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

const STEPS = ['Reading the job description…', 'Extracting missions and requirements…']

export function JobsPage() {
  const add = useAddJob()
  const prev = useRef(add.data)
  useEffect(() => {
    if (add.data && add.data !== prev.current) toast(`Job added: ${add.data.data.title}`)
    prev.current = add.data
  }, [add.data])
  return (
    <Page title="Jobs" description="Add offers, then check how well you fit." wide>
      {add.isError && <ErrorMessage error={add.error} />}
      {add.isPending && <StepProgress steps={STEPS} />}
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground">Your jobs</h2>
          <JobList />
        </section>
        <div className="space-y-6">
          <ManualEntry add={add} />
          <FileEntry add={add} />
          <Search add={add} />
        </div>
      </div>
    </Page>
  )
}
