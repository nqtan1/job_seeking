import { useForm } from 'react-hook-form'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Textarea } from '@/components/ui/textarea'
import { useCreateApplication, useUpdateApplication, type Application } from './api'
import { SOURCES, sourceLabel, toLocalInput } from './constants'

type Values = {
  company_name: string
  job_title: string
  source: (typeof SOURCES)[number]
  status: 'to_apply' | 'applied'
  applied_at: string
  interview_at: string
  contact: string
  notes: string
  location: string
}

const toIso = (local: string) => (local ? new Date(local).toISOString() : null)

function Field({
  id,
  label,
  className,
  children,
}: {
  id: string
  label: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={`space-y-1 ${className ?? ''}`}>
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  )
}

/**
 * One form for both flows. Create: company, role, source, status, date, notes.
 * Edit (`app` given): the same plus contact and interview date, sent as one PATCH.
 */
export function ApplicationForm({ app, onDone }: { app?: Application; onDone?: () => void }) {
  const create = useCreateApplication()
  const update = useUpdateApplication()
  const mutation = app ? update : create
  const appliedDefault = app?.applied_at?.slice(0, 10) ?? ''
  const { register, handleSubmit, reset } = useForm<Values>({
    defaultValues: {
      company_name: app?.company_name ?? '',
      job_title: app?.job_title ?? '',
      source: app?.source ?? 'other',
      status: 'to_apply',
      applied_at: appliedDefault,
      interview_at: toLocalInput(app?.interview_at ?? null),
      contact: app?.contact ?? '',
      notes: app?.notes ?? '',
      location: app?.location ?? '',
    },
  })
  const p = app ? `edit-${app.id}-` : 'new-'

  const submit = handleSubmit((v) => {
    if (app) {
      update.mutate(
        {
          id: app.id,
          changes: {
            company_name: v.company_name,
            job_title: v.job_title || null,
            source: v.source,
            // Only send the date when edited, so an untouched form never rewrites the timestamp.
            ...(v.applied_at !== appliedDefault && { applied_at: toIso(v.applied_at) }),
            notes: v.notes || null,
            location: v.location || null,
            contact: v.contact || null,
            interview_at: toIso(v.interview_at),
          },
        },
        { onSuccess: onDone },
      )
    } else {
      create.mutate(
        {
          company_name: v.company_name,
          job_title: v.job_title || null,
          source: v.source,
          status: v.status,
          ...(v.applied_at && { applied_at: toIso(v.applied_at) }),
          notes: v.notes || null,
          location: v.location || null,
        },
        {
          onSuccess: () => {
            reset()
            onDone?.()
          },
        },
      )
    }
  })

  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={submit} noValidate>
      <Field id={`${p}company`} label="Company">
        <Input
          id={`${p}company`}
          autoComplete="organization"
          {...register('company_name', { required: true })}
        />
      </Field>
      <Field id={`${p}title`} label="Job title">
        <Input id={`${p}title`} {...register('job_title')} />
      </Field>
      <Field id={`${p}source`} label="Source">
        <NativeSelect id={`${p}source`} className="w-full" {...register('source')}>
          {SOURCES.map((s) => (
            <NativeSelectOption key={s} value={s}>
              {sourceLabel(s)}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </Field>
      {!app && (
        <Field id={`${p}status`} label="Status">
          <NativeSelect id={`${p}status`} className="w-full" {...register('status')}>
            <NativeSelectOption value="to_apply">To apply</NativeSelectOption>
            <NativeSelectOption value="applied">Applied</NativeSelectOption>
          </NativeSelect>
        </Field>
      )}
      <Field id={`${p}applied`} label="Applied on">
        <Input id={`${p}applied`} type="date" {...register('applied_at')} />
      </Field>
      <Field id={`${p}location`} label="Location">
        <Input id={`${p}location`} placeholder="City, remote…" {...register('location')} />
      </Field>
      {app && (
        <>
          <Field id={`${p}interview`} label="Interview">
            <Input id={`${p}interview`} type="datetime-local" {...register('interview_at')} />
          </Field>
          <Field id={`${p}contact`} label="Contact">
            <Input id={`${p}contact`} placeholder="Name, email or phone" {...register('contact')} />
          </Field>
        </>
      )}
      <Field id={`${p}notes`} label="Notes" className="sm:col-span-2">
        <Textarea id={`${p}notes`} rows={3} {...register('notes')} />
      </Field>
      {mutation.isError && (
        <div className="sm:col-span-2">
          <ErrorMessage error={mutation.error} />
        </div>
      )}
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" disabled={mutation.isPending}>
          {app ? 'Save' : mutation.isPending ? 'Adding…' : 'Add application'}
        </Button>
        {onDone && (
          <Button type="button" variant="outline" onClick={onDone}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  )
}
