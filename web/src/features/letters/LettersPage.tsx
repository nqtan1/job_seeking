import { FileText } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { StepProgress } from '@/components/StepProgress'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { useJobs } from '@/features/job-search/api'
import { DeleteLetterButton } from './DeleteLetterButton'
import { useCreateLetter, useLetters, type LetterIn } from './api'

const OPTIONS = {
  language: ['fr', 'en'],
  tone: ['professional', 'warm', 'confident', 'academic', 'formal'],
  length: ['short', 'standard', 'detailed'],
  company_type: ['corporate', 'startup', 'phd'],
  template: ['classic', 'modern', 'compact', 'lettre_fr'],
} as const

const STEPS = [
  'Reading your profile and the job…',
  'Drafting your letter…',
  'Polishing the wording…',
]

function NewLetter() {
  const jobs = useJobs()
  const create = useCreateLetter()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { register, handleSubmit } = useForm<LetterIn>({
    defaultValues: {
      job_id: params.get('job') ?? '',
      language: 'fr',
      tone: 'professional',
      length: 'standard',
      company_type: 'corporate',
      template: 'classic',
    },
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>New cover letter</CardTitle>
      </CardHeader>
      <CardContent>
        {jobs.data?.length === 0 ? (
          <p className="text-muted-foreground">
            Add a job first on the{' '}
            <Link to="/jobs" className="underline">
              Jobs
            </Link>{' '}
            page.
          </p>
        ) : (
          <form
            className="grid gap-3 sm:grid-cols-3"
            onSubmit={handleSubmit((v) =>
              create.mutate(v, { onSuccess: (l) => navigate(`/letters/${l.id}`) }),
            )}
          >
            <div className="space-y-1 sm:col-span-3">
              <Label htmlFor="job_id">Job</Label>
              <NativeSelect
                id="job_id"
                className="w-full"
                {...register('job_id', { required: true })}
              >
                <NativeSelectOption value="" disabled>
                  Choose a job…
                </NativeSelectOption>
                {jobs.data?.map((j) => (
                  <NativeSelectOption key={j.id} value={j.id}>
                    {j.data.title} — {j.data.company.name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
            {(Object.keys(OPTIONS) as (keyof typeof OPTIONS)[]).map((k) => (
              <div className="space-y-1" key={k}>
                <Label htmlFor={k}>
                  {k.replace('_', ' ').replace(/^./, (c) => c.toUpperCase())}
                </Label>
                <NativeSelect id={k} className="w-full" {...register(k)}>
                  {OPTIONS[k].map((o) => (
                    <NativeSelectOption key={o}>{o}</NativeSelectOption>
                  ))}
                </NativeSelect>
              </div>
            ))}
            {create.isPending && (
              <div className="sm:col-span-3">
                <StepProgress steps={STEPS} />
              </div>
            )}
            {create.isError && <ErrorMessage error={create.error} />}
            <Button type="submit" className="sm:w-fit" disabled={create.isPending}>
              {create.isPending ? 'Writing your letter…' : 'Generate letter'}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  )
}

export function LettersPage() {
  const letters = useLetters()
  return (
    <Page title="Letters" description="Cover letters tailored to a job and your profile.">
      <NewLetter />
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-muted-foreground">Your letters</h2>
        {letters.isPending && <ListSkeleton rows={2} />}
        {letters.isError && <ErrorMessage error={letters.error} />}
        {letters.data?.length === 0 && (
          <EmptyState
            icon={FileText}
            title="No letters yet"
            description="Pick a job above and generate your first letter."
          />
        )}
        <ul className="space-y-2">
          {letters.data?.map((l) => (
            <li
              key={l.id}
              className="flex items-center gap-2 rounded-xl border bg-card shadow-xs transition-colors hover:bg-accent/50"
            >
              <Link to={`/letters/${l.id}`} className="block min-w-0 flex-1 p-4">
                <p className="font-medium">{l.content.subject || 'Untitled letter'}</p>
                <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                  <StatusBadge tone="info">{l.language}</StatusBadge>
                  <StatusBadge>{l.tone}</StatusBadge>
                  {new Date(l.updated_at).toLocaleDateString()}
                </p>
              </Link>
              <div className="pr-4">
                <DeleteLetterButton id={l.id} />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </Page>
  )
}
