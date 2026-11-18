import { CircleAlert } from 'lucide-react'
import { useEffect } from 'react'
import { useRouteError } from 'react-router'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/EmptyState'
import { useT } from '@/i18n'
import { report } from '@/lib/sentry'

/** Router `errorElement`: a render or chunk-load error shows this instead of a blank page. */
export function ErrorScreen() {
  const error = useRouteError()
  const t = useT()
  const requestId = (error as { request_id?: string } | null)?.request_id
  useEffect(() => report(error, requestId), [error, requestId])
  return (
    <main className="grid min-h-dvh place-items-center p-4">
      <EmptyState
        icon={CircleAlert}
        title={t('err.crash')}
        description={requestId ? t('err.request_id', { id: requestId }) : undefined}
        action={<Button onClick={() => window.location.reload()}>{t('err.reload')}</Button>}
      />
    </main>
  )
}
