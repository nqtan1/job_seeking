import { CircleCheck } from 'lucide-react'
import { useSyncExternalStore } from 'react'
import { snapshot, subscribe } from '@/lib/toast'

export function Toaster() {
  const list = useSyncExternalStore(subscribe, snapshot)
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed right-4 bottom-4 z-50 flex flex-col gap-2"
    >
      {list.map((t) => (
        <p
          key={t.id}
          className="pointer-events-auto flex items-center gap-2 rounded-lg bg-foreground px-3 py-2 text-sm text-background shadow-lg"
        >
          <CircleCheck className="size-4 text-success" />
          {t.text}
        </p>
      ))}
    </div>
  )
}
