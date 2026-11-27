import { useEffect, useRef } from 'react'

/** A native modal <dialog>: focus trap, Escape and `aria-modal` come from the platform.
 *  `side`: a full-height panel sliding in from the right (detail views), not a centred box. */
export function Modal({
  open,
  label,
  onClose,
  side,
  children,
}: {
  open: boolean
  label: string
  onClose?: () => void
  side?: boolean
  children: React.ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      aria-label={label}
      onCancel={(e) => {
        e.preventDefault()
        onClose?.()
      }}
      onClick={(e) => side && e.target === e.currentTarget && onClose?.()} // a click on the backdrop
      className={
        side
          ? 'm-0 ms-auto h-dvh max-h-none w-full max-w-xl border-s bg-background p-0 text-foreground shadow-xl backdrop:bg-black/40 motion-safe:animate-in motion-safe:slide-in-from-right'
          : 'm-auto w-full max-w-sm rounded-lg border bg-background p-6 text-foreground shadow-xl backdrop:bg-black/40'
      }
    >
      {open && children}
    </dialog>
  )
}
