import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useT } from '@/i18n'
import { useDeleteConversation } from './api'

/** Two clicks: "Delete chat", then "Confirm delete" (nothing is undone by one stray click). */
export function DeleteChatButton({ id, onDeleted }: { id: string; onDeleted: () => void }) {
  const t = useT()
  const del = useDeleteConversation()
  const [confirming, setConfirming] = useState(false)
  return confirming ? (
    <span className="flex items-center gap-1">
      <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
        {t('coach.delete.cancel')}
      </Button>
      <Button
        size="sm"
        variant="destructive"
        disabled={del.isPending}
        onClick={() => del.mutate(id, { onSuccess: onDeleted })}
      >
        {del.isPending ? t('coach.delete.deleting') : t('coach.delete.confirm')}
      </Button>
    </span>
  ) : (
    <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>
      <Trash2 /> {t('coach.delete')}
    </Button>
  )
}
