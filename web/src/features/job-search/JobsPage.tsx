import { ContractPicker } from '@/components/ContractPicker'
import { PlacePicker } from '@/components/PlacePicker'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { StepProgress } from '@/components/StepProgress'
import { ApplyActions } from '@/features/pipeline/ApplyActions'
import { usePipeline } from '@/features/pipeline/api'
import { useRadarJobIds } from '@/features/radar/api'
import { Briefcase, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Controller, useForm } from 'react-hook-form'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DeleteJobButton } from './DeleteJobButton'
import { isStale, postingAgeDays } from './age'
import {
  MAX_FILES,
  useAddJob,
  useAddJobFiles,
  useJobs,
  useParseQuery,
  useSearchJobs,
  type SearchParams,
} from './api'

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
          <Button type="submit" loading={add.isPending}>
            {add.isPending ? 'Analysing…' : 'Add job'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

const ACCEPT =
  '.pdf,.docx,.txt,.png,.jpg,.jpeg,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,image/png,image/jpeg'
// Keep in step with ACCEPT and the backend allowlist (documents/service.py). Dropped files
// bypass the dialog's `accept`, so they are checked here; a screenshot may have no extension.
const ALLOWED_NAME = /\.(pdf|docx|txt|png|jpe?g)$/i
const ALLOWED_TYPE = new Set([
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'image/png',
  'image/jpeg',
])
const isAllowed = (f: File) => ALLOWED_NAME.test(f.name) || ALLOWED_TYPE.has(f.type)
const fileKey = (f: File) => `${f.name}|${f.size}|${f.lastModified}`

function FileEntry() {
  const add = useAddJobFiles()
  const [files, setFiles] = useState<File[]>([])
  const [skipped, setSkipped] = useState<string[]>([])
  const [dragging, setDragging] = useState(false)
  const tooMany = files.length > MAX_FILES

  // Every pick (dialog or drop) ADDS to the batch: the user builds it up in as many picks as
  // they like; a file already in the batch is not added twice.
  const addFiles = (picked: File[]) => {
    const ok = picked.filter(isAllowed)
    setSkipped(picked.filter((f) => !isAllowed(f)).map((f) => f.name))
    setFiles((cur) => {
      const seen = new Set(cur.map(fileKey))
      return [...cur, ...ok.filter((f) => !seen.has(fileKey(f)))]
    })
    add.reset()
  }
  const clear = () => {
    setFiles([])
    setSkipped([])
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload job description files</CardTitle>
        <CardDescription>
          PDF, Word, TXT, PNG or JPEG, up to {MAX_FILES} files at once. They are read together:
          pages of one offer become one job, and every distinct offer becomes its own job.
        </CardDescription>
      </CardHeader>
      <CardContent
        className={`space-y-3 transition-colors ${dragging ? 'bg-accent/40' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={(e) => {
          // Moving over a child fires dragleave too: only a real exit ends the highlight.
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false)
        }}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          addFiles([...e.dataTransfer.files])
        }}
      >
        <Label htmlFor="jd-file">Job description files</Label>
        <Input
          id="jd-file"
          type="file"
          multiple
          accept={ACCEPT}
          onChange={(e) => {
            addFiles([...(e.target.files ?? [])])
            e.target.value = '' // so choosing the same file again still fires onChange
          }}
        />
        <p className="text-xs text-muted-foreground">
          Select several at once, pick again to add more, or drop files here.
        </p>
        {files.length > 0 && (
          <ul className="space-y-1 text-sm">
            {files.map((f) => (
              <li key={fileKey(f)} className="flex items-center justify-between gap-2">
                <span className="truncate">{f.name}</span>
                <Button
                  size="icon-xs"
                  variant="ghost"
                  aria-label={`Remove ${f.name}`}
                  disabled={add.isPending}
                  onClick={() => setFiles((cur) => cur.filter((x) => x !== f))}
                >
                  <X />
                </Button>
              </li>
            ))}
          </ul>
        )}
        {skipped.length > 0 && (
          <p role="alert" className="text-sm text-destructive">
            Skipped {skipped.join(', ')}: only PDF, Word, TXT, PNG or JPEG are accepted.
          </p>
        )}
        {tooMany && (
          <p role="alert" className="text-sm text-destructive">
            Choose at most {MAX_FILES} files: remove {files.length - MAX_FILES}.
          </p>
        )}
        {add.isPending && <StepProgress steps={STEPS} />}
        {add.isError && <ErrorMessage error={add.error} />}
        <div className="flex items-center gap-2">
          <Button
            loading={add.isPending}
            disabled={files.length === 0 || tooMany}
            onClick={() =>
              add.mutate(files, {
                onSuccess: clear,
              })
            }
          >
            {add.isPending ? 'Analysing…' : 'Upload and add'}
          </Button>
          {files.length > 0 && !add.isPending && (
            <Button variant="ghost" onClick={clear}>
              Clear
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function Search({ add }: { add: ReturnType<typeof useAddJob> }) {
  const [params, setParams] = useState<SearchParams>()
  const search = useSearchJobs(params)
  const { register, handleSubmit, control, setValue } = useForm<SearchParams>()
  const parse = useParseQuery()
  const [sentence, setSentence] = useState('')
  return (
    <Card>
      <CardHeader>
        <CardTitle>Search France Travail</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <Label htmlFor="sentence">Describe what you are looking for</Label>
          <div className="flex gap-2">
            <Input
              id="sentence"
              value={sentence}
              maxLength={300}
              placeholder="Data analyst in Lyon, CDI, remote"
              onChange={(e) => setSentence(e.target.value)}
            />
            <Button
              type="button"
              variant="outline"
              disabled={parse.isPending || sentence.trim().length < 3}
              onClick={() =>
                parse.mutate(sentence.trim(), {
                  onSuccess: (f) => {
                    setValue('query', f.query ?? '')
                    setValue('department', f.department ?? undefined)
                    setValue('contract_type', f.contract_type ?? undefined)
                  },
                })
              }
            >
              {parse.isPending ? 'Reading…' : 'Fill the filters'}
            </Button>
          </div>
          {parse.isError && <ErrorMessage error={parse.error} />}
          {parse.data && (
            <p className="text-xs text-muted-foreground">
              Check the filters below, then search.
              {parse.data.remote && ' Remote work is not a filter here: look for it in the offers.'}
              {parse.data.notes.length > 0 && ` Not filterable: ${parse.data.notes.join('; ')}.`}
            </p>
          )}
        </div>
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
        <ul className="max-h-96 space-y-2 overflow-y-auto pr-1">
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
      <ul className="max-h-[70vh] space-y-2 overflow-y-auto pr-1" aria-label="Your jobs">
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
                    {isStale(postingAgeDays(j.data.source_meta.posted_on)) && (
                      <StatusBadge tone="warning">
                        Posted {postingAgeDays(j.data.source_meta.posted_on)} days ago: may be
                        filled
                      </StatusBadge>
                    )}
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
                <Link
                  to={`/?job=${j.id}`}
                  className={buttonVariants({ variant: 'outline', size: 'sm' })}
                >
                  Discuss this job
                </Link>
                <ApplyActions
                  jobId={j.id}
                  jobSource={j.source}
                  pdfDocumentId={letters[0]?.pdf_document_id}
                />
                <DeleteJobButton id={j.id} title={j.data.title} />
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
          <FileEntry />
          <Search add={add} />
        </div>
      </div>
    </Page>
  )
}
