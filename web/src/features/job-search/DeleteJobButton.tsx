import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { useT } from '@/i18n'
import { useDeleteJob } from './api'

/** Two steps, with what is lost said before the second click: a job is not one stray click. */
export function DeleteJobButton({
  id,
  title,
  onDeleted,
}: {
  id: string
  title: string
  onDeleted?: () => void
}) {
  const t = useT()
  const del = useDeleteJob()
  const [confirming, setConfirming] = useState(false)
  if (!confirming)
    return (
      <Button
        size="sm"
        variant="outline"
        aria-label={t('jobs.delete_aria', { title })}
        onClick={() => setConfirming(true)}
      >
        {t('jobs.delete')}
      </Button>
    )
  return (
    <div className="w-full space-y-2 rounded-lg border border-destructive/40 p-3 text-sm">
      <p>{t('jobs.delete_confirm_text')}</p>
      {del.isError && <ErrorMessage error={del.error} />}
      <div className="flex gap-2">
        <Button
          size="sm"
          variant="destructive"
          loading={del.isPending}
          onClick={() => del.mutate(id, { onSuccess: onDeleted })}
        >
          {del.isPending ? t('jobs.deleting') : t('jobs.delete_confirm')}
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={del.isPending}
          onClick={() => setConfirming(false)}
        >
          {t('jobs.cancel')}
        </Button>
      </div>
    </div>
  )
}
