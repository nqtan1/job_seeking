import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useDeleteConversation } from './api'

/** Two clicks: "Delete chat", then "Confirm delete" (nothing is undone by one stray click). */
export function DeleteChatButton({ id, onDeleted }: { id: string; onDeleted: () => void }) {
  const del = useDeleteConversation()
  const [confirming, setConfirming] = useState(false)
  return confirming ? (
    <span className="flex items-center gap-1">
      <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
        Cancel
      </Button>
      <Button
        size="sm"
        variant="destructive"
        disabled={del.isPending}
        onClick={() => del.mutate(id, { onSuccess: onDeleted })}
      >
        {del.isPending ? 'Deleting…' : 'Confirm delete'}
      </Button>
    </span>
  ) : (
    <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>
      <Trash2 /> Delete chat
    </Button>
  )
}
