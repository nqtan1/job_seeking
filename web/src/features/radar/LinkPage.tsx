import { useState } from 'react'
import { useT } from '@/i18n'
import { Button } from '@/components/ui/button'

/** Reached from an e-mail, no sign-in. The token stays in the URL fragment (never sent to a
 *  server or logged); a click POSTs it. It shows nothing about any account. */
export function LinkPage() {
  const t = useT()
  const token = new URLSearchParams(window.location.hash.slice(1)).get('t')
  const [state, setState] = useState<'idle' | 'busy' | 'done' | 'failed'>('idle')
  const submit = async () => {
    setState('busy')
    try {
      const r = await fetch('/api/public/radar-link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      setState(r.ok ? 'done' : 'failed')
    } catch {
      setState('failed')
    }
  }
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 p-6">
      <h1 className="text-xl font-semibold">{t('radar.link.title')}</h1>
      {state === 'done' ? (
        <p role="status">{t('radar.link.done')}</p>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">{t('radar.link.confirm')}</p>
          {state === 'failed' && (
            <p role="alert" className="text-sm text-destructive">
              {t('radar.link.failed')}
            </p>
          )}
          <Button disabled={!token || state === 'busy'} onClick={submit}>
            {t('radar.link.button')}
          </Button>
        </>
      )}
    </main>
  )
}
