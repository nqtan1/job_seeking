import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

/** The one "something is running" icon. Reduced-motion users get a still icon (index.css). */
export function Spinner({ className }: { className?: string }) {
  return <Loader2 aria-hidden className={cn('size-4 animate-spin', className)} />
}
