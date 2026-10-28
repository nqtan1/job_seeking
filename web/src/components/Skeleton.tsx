import { useT } from '@/i18n'
import { cn } from 'cn'

export const Skeleton = ({ className }: { className?: string }) => (
  <div aria-hidden className={cn('animate-pulse rounded-md bg-muted', className)} />
)

/** A few card-shaped placeholders while a list loads. */
export function ListSkeleton({ rows = 3 }: { rows?: number }) {
  const t = useT()
  return (
    <div role="status" aria-label={t('app.loading').replace('…', '')} className="space-y-2">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-16 w-full" />
      ))}
    </div>
  )
}
