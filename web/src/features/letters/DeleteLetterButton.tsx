import { ConfirmButton } from '@/components/ConfirmButton'
import { useT } from '@/i18n'
import { useDeleteLetter } from './api'

/** Two clicks: "Delete", then "Confirm delete" (nothing is undone by one stray click). */
export function DeleteLetterButton({ id, onDeleted }: { id: string; onDeleted?: () => void }) {
  const t = useT()
  const del = useDeleteLetter()
  return (
    <ConfirmButton
      label={t('letters.delete')}
      confirmLabel={t('letters.delete.confirm')}
      pendingLabel={t('letters.delete.deleting')}
      pending={del.isPending}
      onConfirm={() => del.mutate(id, { onSuccess: onDeleted })}
    />
  )
}
