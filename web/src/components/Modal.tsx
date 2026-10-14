import { useEffect, useRef } from 'react'

/** A native modal <dialog>: focus trap, Escape and `aria-modal` come from the platform. */
export function Modal({
  open,
  label,
  onClose,
  children,
}: {
  open: boolean
  label: string
  onClose?: () => void
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
      className="m-auto w-full max-w-sm rounded-lg border bg-background p-6 text-foreground shadow-xl backdrop:bg-black/40"
    >
      {open && children}
    </dialog>
  )
}
