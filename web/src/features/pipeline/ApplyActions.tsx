import { Link } from 'react-router'
import { ErrorMessage } from '@/components/ErrorMessage'
import { StatusBadge } from '@/components/StatusBadge'
import { Button, buttonVariants } from '@/components/ui/button'
import { toast } from '@/lib/toast'
import { useApply, usePipeline } from './api'
import { ApplyLink } from './ApplyLink'

const LABEL: Record<string, string> = {
  to_apply: 'To apply',
  applied: 'Applied',
  in_review: 'In review',
  interview: 'Interview',
  offer: 'Offer',
  rejected: 'Rejected',
  ghosted: 'Ghosted',
}

/** The last step of the flow: after the fit check and the letter, track the application or mark
 *  it as sent. Once tracked it shows the status and links to the tracker. */
export function ApplyActions({
  jobId,
  jobSource,
  pdfDocumentId,
}: {
  jobId: string
  jobSource?: string
  pdfDocumentId?: string | null
}) {
  const pipeline = usePipeline()
  const apply = useApply()
  const existing = pipeline.application(jobId)
  const siteLink = <ApplyLink jobId={jobId} />
  if (existing)
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Link to="/tracker" className={buttonVariants({ variant: 'outline', size: 'sm' })}>
          <StatusBadge tone="success">{LABEL[existing.status] ?? existing.status}</StatusBadge>
          View in tracker
        </Link>
        {siteLink}
      </div>
    )
  const go = (status: 'to_apply' | 'applied') =>
    apply.mutate(
      {
        jobId,
        status,
        pdfDocumentId,
        source: jobSource === 'france_travail' ? 'france_travail' : 'other',
      },
      {
        onSuccess: () =>
          toast(status === 'applied' ? 'Marked as applied' : 'Added to your tracker'),
      },
    )
  return (
    <div className="flex flex-wrap items-center gap-2">
      {siteLink}
      <Button size="sm" variant="outline" disabled={apply.isPending} onClick={() => go('to_apply')}>
        Add to tracker
      </Button>
      <Button size="sm" disabled={apply.isPending} onClick={() => go('applied')}>
        I applied
      </Button>
      {apply.isError && <ErrorMessage error={apply.error} />}
    </div>
  )
}
