import { useState } from 'react'
import { cn } from 'cn'
import type { Application, Status } from './api'
import { ApplicationCard } from './ApplicationCard'
import type { Attention } from './attention'
import { COLUMNS, DOT } from './constants'

/**
 * Desktop: columns side by side, scrolling in both axes under sticky headers.
 * Mobile: a tab per status; only the selected column shows (same DOM, CSS decides).
 */
export function Board({
  apps,
  attention,
  onOpen,
  onDrop,
}: {
  apps: Application[]
  attention: Map<string, Attention>
  onOpen: (id: string) => void
  onDrop: (status: Status, id: string) => void
}) {
  const [over, setOver] = useState<Status>()
  const [tab, setTab] = useState<Status>(
    () => COLUMNS.find(([s]) => apps.some((a) => a.status === s))![0],
  )
  return (
    <div className="space-y-3">
      <div
        role="tablist"
        aria-label="Status"
        className="-mx-6 flex gap-1 overflow-x-auto px-6 pb-1 md:hidden"
      >
        {COLUMNS.map(([status, label]) => (
          <button
            key={status}
            type="button"
            role="tab"
            aria-selected={tab === status}
            onClick={() => setTab(status)}
            className={cn(
              'flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
              tab === status ? 'border-primary bg-primary text-primary-foreground' : 'bg-card',
            )}
          >
            {label}
            <span className="text-xs opacity-80">
              {apps.filter((a) => a.status === status).length}
            </span>
          </button>
        ))}
      </div>
      <div className="md:flex md:max-h-[calc(100dvh-14rem)] md:min-h-80 md:gap-3 md:overflow-auto md:pb-2">
        {COLUMNS.map(([status, label]) => {
          const items = apps.filter((a) => a.status === status)
          return (
            <section
              key={status}
              aria-label={label}
              onDragOver={(e) => {
                e.preventDefault()
                setOver(status)
              }}
              onDragLeave={() => setOver(undefined)}
              onDrop={(e) => {
                setOver(undefined)
                onDrop(status, e.dataTransfer.getData('text/plain'))
              }}
              className={cn(
                'rounded-xl bg-muted/50 transition-colors md:w-72 md:shrink-0',
                tab === status ? 'block' : 'hidden md:block',
                over === status && 'bg-accent ring-2 ring-primary/40',
              )}
            >
              <h2 className="sticky top-0 z-[1] hidden items-center gap-2 rounded-t-xl bg-muted px-3 py-2 text-sm font-semibold md:flex">
                <span className={cn('size-2 rounded-full', DOT[status])} aria-hidden />
                {label}
                <span className="rounded-full bg-background px-1.5 text-xs text-muted-foreground">
                  {items.length}
                </span>
              </h2>
              <ul className="space-y-2 p-2">
                {items.map((a) => (
                  <ApplicationCard
                    key={a.id}
                    app={a}
                    attention={attention.get(a.id)}
                    onOpen={() => onOpen(a.id)}
                  />
                ))}
              </ul>
              {items.length === 0 && (
                <p className="px-3 pb-4 text-center text-xs text-muted-foreground">
                  Empty. Applications you move to “{label}” show up here.
                </p>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}
