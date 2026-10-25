import { Kanban, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { Skeleton } from '@/components/Skeleton'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useApplications, useChangeStatus, type Status } from './api'
import { ApplicationDrawer } from './ApplicationDrawer'
import { ApplicationForm } from './ApplicationForm'
import { needsAttention } from './attention'
import { Board } from './Board'
import { AttentionPanel, Funnel } from './Insights'

export function TrackerPage() {
  const apps = useApplications()
  const change = useChangeStatus()
  const [adding, setAdding] = useState(false)
  const [openId, setOpenId] = useState<string>()
  const attention = useMemo(
    () => new Map(needsAttention(apps.data ?? []).map((a) => [a.app.id, a])),
    [apps.data],
  )
  const open = apps.data?.find((a) => a.id === openId)
  // Dropping a card on a column is the same call as the move buttons; the server still
  // decides which moves are allowed (`next_statuses`).
  const drop = (status: Status, id: string) => {
    const app = apps.data?.find((a) => a.id === id)
    if (app && app.status !== status && app.next_statuses.includes(status))
      change.mutate({ id, status })
  }
  return (
    <Page
      title="Tracker"
      description="Follow every application from first idea to offer."
      wide
      actions={
        <>
          <Link to="/tracker/proof" className={buttonVariants({ size: 'sm', variant: 'outline' })}>
            Search record
          </Link>
          <Button size="sm" aria-expanded={adding} onClick={() => setAdding(!adding)}>
            <Plus /> Track an application
          </Button>
        </>
      }
    >
      {adding && (
        <Card>
          <CardHeader>
            <CardTitle>Track an application</CardTitle>
          </CardHeader>
          <CardContent>
            <ApplicationForm onDone={() => setAdding(false)} />
          </CardContent>
        </Card>
      )}
      {apps.data && <AttentionPanel apps={apps.data} />}
      <Funnel />
      {apps.isPending && (
        <div role="status" aria-label="Loading" className="flex gap-3 overflow-hidden">
          {[0, 1, 2].map((i) => (
            <div key={i} className="w-full space-y-2 md:w-72 md:shrink-0">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          ))}
        </div>
      )}
      {apps.isError && <ErrorMessage error={apps.error} />}
      {change.isError && <ErrorMessage error={change.error} />}
      {apps.data?.length === 0 && (
        <EmptyState
          icon={Kanban}
          title="No applications yet"
          description="Track your first one to follow it from idea to offer."
          action={
            !adding && (
              <Button onClick={() => setAdding(true)}>
                <Plus /> Track an application
              </Button>
            )
          }
        />
      )}
      {apps.data && apps.data.length > 0 && (
        <Board apps={apps.data} attention={attention} onOpen={setOpenId} onDrop={drop} />
      )}
      {open && <ApplicationDrawer key={open.id} app={open} onClose={() => setOpenId(undefined)} />}
    </Page>
  )
}
