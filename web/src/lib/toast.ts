type Toast = { id: number; text: string }
let toasts: Toast[] = []
let next = 0
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())

/** A short confirmation ("Profile saved."). Errors stay inline, next to what failed. */
export function toast(text: string) {
  const id = next++
  toasts = [...toasts, { id, text }]
  emit()
  setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id)
    emit()
  }, 4000)
}

export const subscribe = (cb: () => void) => (listeners.add(cb), () => void listeners.delete(cb))
export const snapshot = () => toasts
