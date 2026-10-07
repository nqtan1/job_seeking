import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { ContractPicker } from '@/components/ContractPicker'
import { PlacePicker } from '@/components/PlacePicker'
import { placesLabel } from '@/lib/regions'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { StepProgress } from '@/components/StepProgress'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useProfile } from '@/features/candidate/api'
import { useTask } from '@/lib/api/tasks'
import {
  REFRESH_AFTER_RUN,
  useAiUse,
  useCreateSearch,
  useDeleteSearch,
  useRunSearch,
  useSearches,
  useToggleSearch,
  useUpdateSearch,
  type Search,
  type SearchIn,
} from './api'
import { Insights } from './Insights'
import { InProgress, NewMatches, Rejected } from './Matches'
import { StatusStrip } from './StatusStrip'
import { Timeline } from './Timeline'

const MAX_SEARCHES = 3

function SearchForm() {
  const create = useCreateSearch()
  const { register, handleSubmit, reset, control } = useForm<SearchIn>({
    defaultValues: { min_score: 70, daily_limit: 5, enabled: true, contract_type: null },
  })
  return (
    <form
      className="grid gap-3 sm:grid-cols-4"
      onSubmit={handleSubmit((v) =>
        create.mutate(
          {
            ...v,
            query: v.query || null,
            department: v.department || null,
            contract_type: v.contract_type || null,
            min_score: Number(v.min_score),
            daily_limit: Number(v.daily_limit),
          },
          { onSuccess: () => reset() },
        ),
      )}
    >
      <div className="space-y-1">
        <Label htmlFor="r-name">Name</Label>
        <Input id="r-name" placeholder="Python, Paris" {...register('name', { required: true })} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="r-query">Keywords</Label>
        <Input id="r-query" {...register('query')} />
        <p className="text-xs text-muted-foreground">
          Separate alternatives with a comma: IA Engineer, ML Engineer finds either.
        </p>
      </div>
      <div className="space-y-1 sm:col-span-2">
        <Label>Where</Label>
        <Controller
          control={control}
          name="department"
          render={({ field }) => <PlacePicker value={field.value} onChange={field.onChange} />}
        />
      </div>
      <div className="space-y-1 sm:col-span-4">
        <Label>Contract types</Label>
        <Controller
          control={control}
          name="contract_type"
          render={({ field }) => <ContractPicker value={field.value} onChange={field.onChange} />}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="r-score">Minimum fit (%)</Label>
        <Input id="r-score" type="number" min={0} max={100} {...register('min_score')} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="r-limit">Jobs scored per day (1–10)</Label>
        <Input id="r-limit" type="number" min={1} max={10} {...register('daily_limit')} />
      </div>
      {create.isError && (
        <div className="sm:col-span-4">
          <ErrorMessage error={create.error} />
        </div>
      )}
      <Button type="submit" className="sm:w-fit" disabled={create.isPending}>
        {create.isPending ? 'Adding…' : 'Add radar'}
      </Button>
    </form>
  )
}

/** The same fields as a new radar, filled in; saving changes only this radar. */
function EditForm({ search, onDone }: { search: Search; onDone: () => void }) {
  const update = useUpdateSearch()
  const { register, handleSubmit, control } = useForm<SearchIn>({
    defaultValues: {
      name: search.name,
      query: search.query ?? '',
      department: search.department ?? '',
      contract_type: search.contract_type,
      min_score: search.min_score,
      daily_limit: search.daily_limit,
    },
  })
  return (
    <form
      className="grid gap-3 sm:grid-cols-4"
      onSubmit={handleSubmit((v) =>
        update.mutate(
          {
            id: search.id,
            changes: {
              name: v.name,
              query: v.query || null,
              department: v.department || null,
              contract_type: v.contract_type || null,
              min_score: Number(v.min_score),
              daily_limit: Number(v.daily_limit),
            },
          },
          { onSuccess: onDone },
        ),
      )}
    >
      <div className="space-y-1">
        <Label htmlFor={`e-name-${search.id}`}>Name</Label>
        <Input id={`e-name-${search.id}`} {...register('name', { required: true })} />
      </div>
      <div className="space-y-1">
        <Label htmlFor={`e-query-${search.id}`}>Keywords</Label>
        <Input id={`e-query-${search.id}`} {...register('query')} />
        <p className="text-xs text-muted-foreground">
          Separate alternatives with a comma: IA Engineer, ML Engineer finds either.
        </p>
      </div>
      <div className="space-y-1 sm:col-span-2">
        <Label>Where</Label>
        <Controller
          control={control}
          name="department"
          render={({ field }) => <PlacePicker value={field.value} onChange={field.onChange} />}
        />
      </div>
      <div className="space-y-1 sm:col-span-4">
        <Label>Contract types</Label>
        <Controller
          control={control}
          name="contract_type"
          render={({ field }) => <ContractPicker value={field.value} onChange={field.onChange} />}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor={`e-score-${search.id}`}>Minimum fit (%)</Label>
        <Input
          id={`e-score-${search.id}`}
          type="number"
          min={0}
          max={100}
          {...register('min_score')}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor={`e-limit-${search.id}`}>Jobs scored per day (1–10)</Label>
        <Input
          id={`e-limit-${search.id}`}
          type="number"
          min={1}
          max={10}
          {...register('daily_limit')}
        />
      </div>
      {update.isError && (
        <div className="sm:col-span-4">
          <ErrorMessage error={update.error} />
        </div>
      )}
      <div className="flex gap-2 sm:col-span-4">
        <Button type="submit" size="sm" disabled={update.isPending}>
          Save changes
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function SearchCard({ search }: { search: Search }) {
  const run = useRunSearch()
  const task = useTask(run.data?.task_id)
  const del = useDeleteSearch()
  const toggle = useToggleSearch()
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const status = task.data?.status
  const running = run.isPending || status === 'queued'
  useEffect(() => {
    if (status === 'done' || status === 'failed')
      REFRESH_AFTER_RUN.forEach((queryKey) => qc.invalidateQueries({ queryKey }))
  }, [status, qc])
  return (
    <li className="space-y-2 rounded-xl border bg-card p-4 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-medium">{search.name}</p>
          <p className="text-xs text-muted-foreground">
            {[search.query, placesLabel(search.department), search.contract_type]
              .filter(Boolean)
              .join(' · ')}{' '}
            · fit ≥ {search.min_score}% · up to {search.daily_limit} a day
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1 text-xs">
            <input
              type="checkbox"
              checked={search.enabled}
              disabled={toggle.isPending}
              onChange={(e) => toggle.mutate({ id: search.id, enabled: e.target.checked })}
            />
            Daily
          </label>
          <Button size="sm" disabled={running} onClick={() => run.mutate(search.id)}>
            {running ? 'Searching…' : 'Run now'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            aria-label={`Edit ${search.name}`}
            aria-expanded={editing}
            onClick={() => setEditing(!editing)}
          >
            Edit
          </Button>
          <Button
            size="sm"
            variant="outline"
            aria-label={`Delete ${search.name}`}
            disabled={del.isPending}
            onClick={() => del.mutate(search.id)}
          >
            Delete
          </Button>
        </div>
      </div>
      {editing && <EditForm search={search} onDone={() => setEditing(false)} />}
      {running && <StepProgress steps={['Searching offers…', 'Scoring how well you fit…']} />}
      {run.isError && <ErrorMessage error={run.error} />}
      {status === 'failed' && (
        <p role="alert" className="text-sm text-destructive">
          The run failed. Please try again later.
        </p>
      )}
    </li>
  )
}

/** Today's AI use against the daily cap: the radar pauses early so chat and letters still work. */
function AiUse() {
  const use = useAiUse()
  if (!use.data) return null
  return (
    <p className="text-xs text-muted-foreground">
      AI use today: {use.data.used} of {use.data.quota}. Your radar pauses at{' '}
      {use.data.radar_stops_at} so chat and letters keep working.
    </p>
  )
}

function HowItWorks({ open }: { open: boolean }) {
  return (
    <details open={open} className="rounded-xl border bg-card p-4 text-sm">
      <summary className="cursor-pointer font-medium">How the radar works</summary>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
        <li>Every morning it searches France Travail with your keywords.</li>
        <li>It scores how well each new offer fits your profile, a few a day.</li>
        <li>Good fits wait here, with the reasons. You keep, dismiss or review them.</li>
        <li>It never applies for you and never contacts a company.</li>
      </ol>
    </details>
  )
}

/** A one-click first radar from the user's own CV. */
function Starter() {
  const profile = useProfile()
  const create = useCreateSearch()
  const title = profile.data?.data.experiences?.[0]?.job_title
  if (!title) return null
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-primary/30 bg-primary/5 p-4">
      <p className="text-sm">
        Start from your CV: look for <strong>{title}</strong> offers.
      </p>
      <Button
        size="sm"
        disabled={create.isPending}
        onClick={() =>
          create.mutate({ name: title, query: title, min_score: 70, daily_limit: 5, enabled: true })
        }
      >
        Start this radar
      </Button>
      {create.isError && <ErrorMessage error={create.error} />}
    </div>
  )
}

export function RadarPage() {
  const searches = useSearches()
  const [adding, setAdding] = useState(false)
  const count = searches.data?.length ?? 0
  const minScore = searches.data?.[0]?.min_score
  return (
    <Page
      title="Job radar"
      description="Looks for offers every morning and scores how well you fit. You decide what happens next: it never applies for you."
      wide
    >
      <StatusStrip />
      {count > 0 && (
        <>
          <Insights />
          <section aria-label="New matches" className="space-y-3">
            <h2 className="text-sm font-semibold text-muted-foreground">New matches</h2>
            <NewMatches />
          </section>
          <InProgress />
          <Rejected minScore={minScore} />
        </>
      )}
      <section aria-label="Your radars" className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-muted-foreground">Your radars</h2>
          {count < MAX_SEARCHES && (
            <Button size="sm" variant="outline" onClick={() => setAdding(!adding)}>
              {adding ? 'Close' : 'New radar'}
            </Button>
          )}
        </div>
        {count === 0 && !searches.isPending && <Starter />}
        {adding && (
          <Card>
            <CardHeader>
              <CardTitle>New radar</CardTitle>
            </CardHeader>
            <CardContent>
              <SearchForm />
            </CardContent>
          </Card>
        )}
        {searches.isPending && <ListSkeleton rows={1} />}
        {searches.isError && <ErrorMessage error={searches.error} />}
        <ul className="space-y-2">
          {searches.data?.map((s) => (
            <SearchCard key={s.id} search={s} />
          ))}
        </ul>
      </section>
      <Timeline />
      <AiUse />
      <HowItWorks open={count === 0 && !searches.isPending} />
    </Page>
  )
}
