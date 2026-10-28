import { useState, type ComponentProps, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

type Props = {
  label: ReactNode
  confirmLabel: ReactNode
  /** Shown while `pending`; defaults to `confirmLabel`. */
  pendingLabel?: ReactNode
  /** When set, a cancel button is shown (before the confirm one) during the second step. */
  cancelLabel?: ReactNode
  pending?: boolean
  /** Disables both steps (e.g. while something else is busy). */
  disabled?: boolean
  /** Call `reset` to go back to the first step (e.g. from a mutation's `onSettled`). */
  onConfirm: (reset: () => void) => void
  variant?: ComponentProps<typeof Button>['variant']
  className?: string
  'aria-label'?: string
  confirmAriaLabel?: string
}

/** Two clicks for anything destructive: `label`, then `confirmLabel`. */
export function ConfirmButton({
  label,
  confirmLabel,
  pendingLabel,
  cancelLabel,
  pending,
  disabled,
  onConfirm,
  variant = 'outline',
  className,
  confirmAriaLabel,
  ...rest
}: Props) {
  const [confirming, setConfirming] = useState(false)
  if (!confirming)
    return (
      <Button
        size="sm"
        variant={variant}
        className={className}
        disabled={disabled}
        aria-label={rest['aria-label']}
        onClick={() => setConfirming(true)}
      >
        {label}
      </Button>
    )
  const confirm = (
    <Button
      size="sm"
      variant="destructive"
      disabled={disabled || pending}
      aria-label={confirmAriaLabel}
      onClick={() => onConfirm(() => setConfirming(false))}
    >
      {pending ? (pendingLabel ?? confirmLabel) : confirmLabel}
    </Button>
  )
  return cancelLabel ? (
    <span className="flex items-center gap-1">
      <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
        {cancelLabel}
      </Button>
      {confirm}
    </span>
  ) : (
    confirm
  )
}
