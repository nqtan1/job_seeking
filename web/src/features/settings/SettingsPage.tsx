import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { Skeleton } from '@/components/Skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useTask } from '@/lib/api/tasks'
import { signOut } from '@/lib/auth'
import { useDeleteAccount, useMe, useSetReminders, useStartExport } from './api'

const CONFIRM_WORD = 'DELETE'

function RemindersCard() {
  const me = useMe()
  const set = useSetReminders()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Email reminders</CardTitle>
        <CardDescription>
          One short email in the morning when an application has had no reply for a week, or an
          interview is 3 days or 1 day away. Nothing else, and never marketing.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={me.data?.email_reminders ?? true}
            disabled={me.isPending || set.isPending}
            onChange={(e) => set.mutate(e.target.checked)}
          />
          Send me reminders
        </label>
        {set.isError && <ErrorMessage error={set.error} />}
      </CardContent>
    </Card>
  )
}

function ExportCard() {
  const start = useStartExport()
  const task = useTask(start.data?.task_id)
  const running = start.isPending || task.data?.status === 'queued'
  return (
    <Card>
      <CardHeader>
        <CardTitle>Export your data</CardTitle>
        <CardDescription>
          A ZIP with your profile, jobs, letters and applications. The link expires, so download it
          right away.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button disabled={running} onClick={() => start.mutate()}>
          {running ? 'Preparing your export…' : 'Request export'}
        </Button>
        {start.isError && <ErrorMessage error={start.error} />}
        {task.isError && <ErrorMessage error={task.error} />}
        {task.data?.status === 'failed' && (
          <p role="alert" className="text-sm text-destructive">
            The export failed. Please try again.
          </p>
        )}
        {task.data?.status === 'done' && task.data.download_url && (
          <a href={task.data.download_url} download className="text-primary underline">
            Download your export (ZIP)
          </a>
        )}
      </CardContent>
    </Card>
  )
}

function DeleteCard() {
  const del = useDeleteAccount()
  const qc = useQueryClient()
  const [typed, setTyped] = useState('')
  return (
    <Card className="border-destructive/50">
      <CardHeader>
        <CardTitle>Delete your account</CardTitle>
        <CardDescription>
          Permanently deletes your profile, jobs, letters, applications and files, and your sign-in.
          This cannot be undone.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Label htmlFor="confirm">Type {CONFIRM_WORD} to confirm</Label>
        <Input
          id="confirm"
          value={typed}
          autoComplete="off"
          onChange={(e) => setTyped(e.target.value)}
        />
        {del.isError && <ErrorMessage error={del.error} />}
        <Button
          variant="destructive"
          disabled={typed !== CONFIRM_WORD || del.isPending}
          onClick={() =>
            del.mutate(undefined, {
              onSuccess: async () => {
                qc.clear() // no cached data of the deleted account stays in memory
                await signOut().catch(() => {}) // the Firebase user is already gone server-side
              },
            })
          }
        >
          {del.isPending ? 'Deleting…' : 'Delete my account'}
        </Button>
      </CardContent>
    </Card>
  )
}

export function SettingsPage() {
  const me = useMe()
  return (
    <Page title="Settings" description="Your account, your data.">
      <div className="max-w-2xl space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Account</CardTitle>
          </CardHeader>
          <CardContent>
            {me.isPending && <Skeleton className="h-5 w-48" />}
            {me.isError && <ErrorMessage error={me.error} />}
            {me.data && <p>Signed in as {me.data.user.email}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Plan <StatusBadge tone="info">Free</StatusBadge>
            </CardTitle>
            <CardDescription>Paid plans are coming soon.</CardDescription>
          </CardHeader>
        </Card>
        <RemindersCard />
        <ExportCard />
        <DeleteCard />
      </div>
    </Page>
  )
}
