import { X } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'
import { useT } from '@/i18n'
import { Button } from '@/components/ui/button'
import { cn } from 'cn'

/** Side panel: Escape closes, focus moves in and returns to the opener, backdrop click closes. */
export function Drawer({
  label,
  title,
  subtitle,
  side = 'right',
  paused,
  onClose,
  children,
}: {
  label: string
  title: string
  subtitle?: string
  side?: 'left' | 'right'
  /** Ignore Escape while a drawer on top is open. */
  paused?: boolean
  onClose: () => void
  children: ReactNode
}) {
  const t = useT()
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    return () => opener?.focus?.()
  }, [])
  useEffect(() => {
    if (paused) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, paused])
  return (
    <>
      <div aria-hidden className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={label}
        className={cn(
          'fixed inset-y-0 z-50 flex w-full max-w-lg flex-col gap-4 overflow-y-auto bg-background p-4 shadow-xl',
          side === 'left' ? 'left-0 border-r' : 'right-0 border-l',
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="truncate font-semibold">{title}</h2>
            {subtitle && <p className="truncate text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          <Button
            ref={closeRef}
            size="icon-sm"
            variant="ghost"
            aria-label={t('tracker.close')}
            onClick={onClose}
          >
            <X />
          </Button>
        </div>
        {children}
      </aside>
    </>
  )
}
