import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useDeleteLetter } from './api'

/** Two clicks: "Delete", then "Confirm delete" (nothing is undone by one stray click). */
export function DeleteLetterButton({ id, onDeleted }: { id: string; onDeleted?: () => void }) {
  const del = useDeleteLetter()
  const [confirming, setConfirming] = useState(false)
  return confirming ? (
    <Button
      size="sm"
      variant="destructive"
      disabled={del.isPending}
      onClick={() => del.mutate(id, { onSuccess: onDeleted })}
    >
      {del.isPending ? 'Deleting…' : 'Confirm delete'}
    </Button>
  ) : (
    <Button size="sm" variant="outline" onClick={() => setConfirming(true)}>
      Delete
    </Button>
  )
}
