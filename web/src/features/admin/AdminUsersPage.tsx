import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuthUser } from '@/lib/auth'
import { AdminTabs } from './AdminTabs'
import { PAGE, useAdminStats, useAdminUsers, useSetBlocked } from './api'

const num = (n: number) => n.toLocaleString()

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{num(value)}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

/** Platform numbers only: counts, never anyone's content. */
function Overview() {
  const stats = useAdminStats()
  if (stats.isPending) return <ListSkeleton rows={2} />
  if (stats.isError) return <ErrorMessage error={stats.error} />
  const { users, content, applications_by_status: byStatus, ai_last_30d: ai } = stats.data
  const peak = Math.max(1, ...stats.data.signups_by_day.map((d) => d.count))
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Users" value={users.total} hint={`+${users.new_7d} this week`} />
        <Stat
          label="Active (7 days)"
          value={users.active_7d}
          hint={`${users.active_30d} in 30 days`}
        />
        <Stat label="Profiles" value={content.profiles} />
        <Stat label="Jobs saved" value={content.jobs} />
        <Stat label="Letters" value={content.letters} />
        <Stat label="Applications" value={content.applications} />
        <Stat label="New (30 days)" value={users.new_30d} />
      </div>
      <section aria-label="Sign-ups per day">
        <h2 className="mb-2 text-sm font-semibold">Sign-ups, last 30 days</h2>
        {stats.data.signups_by_day.length === 0 ? (
          <p className="text-sm text-muted-foreground">No sign-ups yet.</p>
        ) : (
          <div className="flex h-24 items-end gap-1">
            {stats.data.signups_by_day.map((d) => (
              <div
                key={d.day}
                title={`${d.day}: ${d.count}`}
                style={{ height: `${(d.count / peak) * 100}%` }}
                className="min-h-1 flex-1 rounded-t bg-primary"
              />
            ))}
          </div>
        )}
      </section>
      <div className="grid gap-6 md:grid-cols-2">
        <section aria-label="Applications by status">
          <h2 className="mb-2 text-sm font-semibold">Applications by status</h2>
          <ul className="space-y-1 text-sm">
            {Object.entries(byStatus).map(([s, n]) => (
              <li key={s} className="flex justify-between border-b py-1">
                <span>{s.replace('_', ' ')}</span>
                <span className="tabular-nums">{n}</span>
              </li>
            ))}
            {Object.keys(byStatus).length === 0 && (
              <li className="text-muted-foreground">None yet.</li>
            )}
          </ul>
        </section>
        <section aria-label="AI usage">
          <h2 className="mb-2 text-sm font-semibold">AI usage, last 30 days</h2>
          <ul className="space-y-1 text-sm">
            {ai.map((a) => (
              <li key={a.feature} className="flex justify-between gap-2 border-b py-1">
                <span>{a.feature}</span>
                <span className="tabular-nums text-muted-foreground">
                  {num(a.calls)} calls · {num(a.input_tokens + a.output_tokens)} tokens
                  {a.errors > 0 && ` · ${a.errors} errors`}
                </span>
              </li>
            ))}
            {ai.length === 0 && <li className="text-muted-foreground">No AI calls yet.</li>}
          </ul>
        </section>
      </div>
    </div>
  )
}

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : '—')

/** Admin-only (the API answers 403 to anyone else). Account metadata only, never user content. */
export function AdminUsersPage() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(0)
  const users = useAdminUsers(q, page)
  const setBlocked = useSetBlocked()
  const [confirming, setConfirming] = useState<string>()
  const me = useAuthUser()?.email?.toLowerCase()
  const total = users.data?.total ?? 0
  return (
    <Page
      title="Admin"
      description="How the platform is used. Counts and account details only."
      wide
    >
      <AdminTabs />
      <Overview />
      <h2 className="text-sm font-semibold">Users</h2>
      <Input
        aria-label="Search by email"
        placeholder="Search by email…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setPage(0)
        }}
        className="max-w-sm"
      />
      {users.isPending && <ListSkeleton rows={4} />}
      {users.isError && <ErrorMessage error={users.error} />}
      {setBlocked.isError && <ErrorMessage error={setBlocked.error} />}
      {users.data && (
        <>
          <div className="overflow-x-auto rounded-xl border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="p-3 font-medium">Email</th>
                  <th className="p-3 font-medium">Name</th>
                  <th className="p-3 font-medium">Joined</th>
                  <th className="p-3 font-medium">Last active</th>
                  <th className="p-3 font-medium">Status</th>
                  <th className="p-3" />
                </tr>
              </thead>
              <tbody>
                {users.data.items.map((u) => (
                  <tr key={u.id} className="border-t">
                    <td className="p-3">{u.email}</td>
                    <td className="p-3">{u.display_name ?? '—'}</td>
                    <td className="p-3">{day(u.created_at)}</td>
                    <td className="p-3">{day(u.last_active_at)}</td>
                    <td className="p-3">
                      {u.blocked ? (
                        <span className="text-destructive">Blocked</span>
                      ) : (
                        <span className="text-muted-foreground">Active</span>
                      )}
                    </td>
                    <td className="p-3 text-right">
                      {u.email.toLowerCase() !== me &&
                        (u.blocked ? (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={setBlocked.isPending}
                            aria-label={`Unblock ${u.email}`}
                            onClick={() => setBlocked.mutate({ id: u.id, blocked: false })}
                          >
                            Unblock
                          </Button>
                        ) : confirming === u.id ? (
                          <Button
                            size="sm"
                            variant="destructive"
                            disabled={setBlocked.isPending}
                            aria-label={`Confirm block ${u.email}`}
                            onClick={() =>
                              setBlocked.mutate(
                                { id: u.id, blocked: true },
                                { onSettled: () => setConfirming(undefined) },
                              )
                            }
                          >
                            Confirm block
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            aria-label={`Block ${u.email}`}
                            onClick={() => setConfirming(u.id)}
                          >
                            Block
                          </Button>
                        ))}
                    </td>
                  </tr>
                ))}
                {users.data.items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="p-6 text-center text-muted-foreground">
                      No users found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {total} user{total === 1 ? '' : 's'}
            </span>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={(page + 1) * PAGE >= total}
                onClick={() => setPage(page + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </Page>
  )
}
