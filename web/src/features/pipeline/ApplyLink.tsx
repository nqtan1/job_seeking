import { buttonVariants } from '@/components/ui/button'
import { useApplyUrl } from '@/features/job-search/api'

/** "Apply on site": the real offer page, when the job came with one. */
export function ApplyLink({ jobId }: { jobId: string | null | undefined }) {
  const url = useApplyUrl(jobId)
  if (!url) return null
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={buttonVariants({ variant: 'outline', size: 'sm' })}
    >
      Apply on site
    </a>
  )
}
