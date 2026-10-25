import { Pencil, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { usePatchJob, type Job } from './api'
import { missingOf } from './label'

/** "Missing: company / address — Add" (or "Edit" when complete) opening a small inline form. */
export function JobDetailsFix({ job }: { job: Job }) {
  const [open, setOpen] = useState(false)
  const patch = usePatchJob(job.id)
  const missing = missingOf(job)
  const { register, handleSubmit } = useForm({
    defaultValues: {
      company_name: job.data.company.name ?? '',
      company_address: job.data.company.address ?? '',
      location: job.data.badges.location ?? '',
    },
  })
  const p = `job-${job.id}-`
  return (
    <div className="space-y-2">
      {!open && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {missing.length > 0 && (
            <span className="flex items-center gap-1 text-warning">
              <TriangleAlert className="size-3.5" aria-hidden /> Missing: {missing.join(' / ')}
            </span>
          )}
          <Button size="xs" variant="outline" onClick={() => setOpen(true)}>
            {missing.length > 0 ? (
              'Add'
            ) : (
              <>
                <Pencil /> Edit details
              </>
            )}
          </Button>
        </div>
      )}
      {open && (
        <form
          className="grid gap-2 rounded-lg border bg-muted/30 p-3 sm:grid-cols-2"
          onSubmit={handleSubmit((v) => patch.mutate(v, { onSuccess: () => setOpen(false) }))}
        >
          <div className="space-y-1">
            <Label htmlFor={`${p}company`}>Company</Label>
            <Input id={`${p}company`} {...register('company_name')} />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`${p}location`}>Location</Label>
            <Input id={`${p}location`} placeholder="City" {...register('location')} />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor={`${p}address`}>Company address</Label>
            <Input id={`${p}address`} {...register('company_address')} />
          </div>
          {patch.isError && (
            <div className="sm:col-span-2">
              <ErrorMessage error={patch.error} />
            </div>
          )}
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" size="sm" loading={patch.isPending}>
              Save
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </div>
  )
}
