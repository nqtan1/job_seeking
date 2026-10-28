import { Trash2 } from 'lucide-react'
import { ConfirmButton } from '@/components/ConfirmButton'
import { useT } from '@/i18n'
import { useDeleteConversation } from './api'

/** Two clicks: "Delete chat", then "Confirm delete" (nothing is undone by one stray click). */
export function DeleteChatButton({ id, onDeleted }: { id: string; onDeleted: () => void }) {
  const t = useT()
  const del = useDeleteConversation()
  return (
    <ConfirmButton
      variant="ghost"
      label={
        <>
          <Trash2 /> {t('coach.delete')}
        </>
      }
      confirmLabel={t('coach.delete.confirm')}
      pendingLabel={t('coach.delete.deleting')}
      cancelLabel={t('coach.delete.cancel')}
      pending={del.isPending}
      onConfirm={() => del.mutate(id, { onSuccess: onDeleted })}
    />
  )
}
