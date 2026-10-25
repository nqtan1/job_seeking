import { useEffect, useState } from 'react'
import { useMe } from '@/features/settings/api'

/** The API scales to zero: the first call after a quiet period can take ~15 s. Say so instead of
 *  leaving a blank screen, but only once it is actually slow. */
export function ColdStartNotice() {
  const pending = useMe().isPending
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    if (!pending) return
    const t = setTimeout(() => setSlow(true), 3000)
    return () => clearTimeout(t)
  }, [pending])
  if (!pending || !slow) return null
  return (
    <p role="status" className="border-b bg-muted px-4 py-2 text-sm text-muted-foreground">
      Waking up the server — this takes a few seconds after a quiet period.
    </p>
  )
}
