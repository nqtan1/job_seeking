import { useEffect, useState } from 'react'

/** Progress for a slow AI task. The API gives no progress, so the steps are a reassurance that
 *  advances with time (the last one stays until the task ends). */
export function StepProgress({ steps, every = 7000 }: { steps: string[]; every?: number }) {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((n) => Math.min(n + 1, steps.length - 1)), every)
    return () => clearInterval(t)
  }, [steps.length, every])
  return (
    <div role="status" className="space-y-2 rounded-lg bg-accent/60 p-3 text-sm">
      <p className="font-medium text-accent-foreground">{steps[i]}</p>
      <div className="h-1 overflow-hidden rounded-full bg-accent">
        <div className="h-full w-1/3 animate-[indeterminate_1.6s_ease-in-out_infinite] rounded-full bg-primary" />
      </div>
      <p className="text-xs text-muted-foreground">This can take up to a minute.</p>
    </div>
  )
}
