import { Check, Circle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Spinner } from '@/components/Spinner'

/** Progress for a slow AI task. The API reports no progress, so the steps are a reassurance
 *  that advances with time (the last one stays until the task ends) and the timer is the only
 *  hard fact shown: it never claims a percentage it does not know. */
export function StepProgress({ steps, every = 7000 }: { steps: string[]; every?: number }) {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [])
  const current = Math.min(Math.floor((seconds * 1000) / every), steps.length - 1)
  return (
    <div role="status" className="space-y-3 rounded-lg bg-accent/60 p-3 text-sm">
      {/* Screen readers hear the current step only; the list below is the visual version. */}
      <p className="sr-only">{steps[current]}</p>
      <ol aria-hidden className="space-y-1.5">
        {steps.map((step, i) => (
          <li
            key={step}
            className={`flex items-center gap-2 ${
              i === current ? 'font-medium text-accent-foreground' : 'text-muted-foreground'
            }`}
          >
            {i < current ? (
              <Check className="size-4 text-primary" />
            ) : i === current ? (
              <Spinner className="text-primary" />
            ) : (
              <Circle className="size-4 opacity-40" />
            )}
            {step}
          </li>
        ))}
      </ol>
      <div aria-hidden className="h-1 overflow-hidden rounded-full bg-accent">
        <div className="h-full w-1/3 animate-[indeterminate_1.6s_ease-in-out_infinite] rounded-full bg-primary" />
      </div>
      <p aria-hidden className="text-xs text-muted-foreground tabular-nums">
        {seconds} s · this can take up to a minute
      </p>
    </div>
  )
}
