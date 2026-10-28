import { useState } from 'react'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/i18n'
import { STATUS_KEY } from '@/features/tracker/constants'
import type { Status } from '@/features/tracker/api'
import { useAuthUser } from '@/lib/auth'
import { AdminTabs } from './AdminTabs'
import { PAGE, useAdminStats, useAdminUsers, useSetBlocked } from './api'

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  const { locale } = useI18n()
  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value.toLocaleString(locale)}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

/** Platform numbers only: counts, never anyone's content. */
function Overview() {
  const { t, locale } = useI18n()
  const num = (n: number) => n.toLocaleString(locale)
  const stats = useAdminStats()
  if (stats.isPending) return <ListSkeleton rows={2} />
  if (stats.isError) return <ErrorMessage error={stats.error} />
  const { users, content, applications_by_status: byStatus, ai_last_30d: ai } = stats.data
  const peak = Math.max(1, ...stats.data.signups_by_day.map((d) => d.count))
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label={t('admin.stat.users')}
          value={users.total}
          hint={t('admin.stat.new_week', { n: users.new_7d })}
        />
        <Stat
          label={t('admin.stat.active7')}
          value={users.active_7d}
          hint={t('admin.stat.active30', { n: users.active_30d })}
        />
        <Stat label={t('admin.stat.profiles')} value={content.profiles} />
        <Stat label={t('admin.stat.jobs')} value={content.jobs} />
        <Stat label={t('admin.stat.letters')} value={content.letters} />
        <Stat label={t('admin.stat.applications')} value={content.applications} />
        <Stat label={t('admin.stat.new30')} value={users.new_30d} />
      </div>
      <section aria-label={t('admin.signups_aria')}>
        <h2 className="mb-2 text-sm font-semibold">{t('admin.signups')}</h2>
        {stats.data.signups_by_day.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('admin.no_signups')}</p>
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
        <section aria-label={t('admin.apps_by_status')}>
          <h2 className="mb-2 text-sm font-semibold">{t('admin.apps_by_status')}</h2>
          <ul className="space-y-1 text-sm">
            {Object.entries(byStatus).map(([s, n]) => (
              <li key={s} className="flex justify-between border-b py-1">
                <span>{s in STATUS_KEY ? t(STATUS_KEY[s as Status]) : s.replace('_', ' ')}</span>
                <span className="tabular-nums">{n}</span>
              </li>
            ))}
            {Object.keys(byStatus).length === 0 && (
              <li className="text-muted-foreground">{t('admin.none_yet')}</li>
            )}
          </ul>
        </section>
        <section aria-label={t('admin.ai_usage_aria')}>
          <h2 className="mb-2 text-sm font-semibold">{t('admin.ai_usage')}</h2>
          <ul className="space-y-1 text-sm">
            {ai.map((a) => (
              <li key={a.feature} className="flex justify-between gap-2 border-b py-1">
                <span>{a.feature}</span>
                <span className="tabular-nums text-muted-foreground">
                  {t('admin.ai_row', {
                    calls: num(a.calls),
                    tokens: num(a.input_tokens + a.output_tokens),
                  })}
                  {a.errors > 0 && t('admin.ai_errors', { n: a.errors })}
                </span>
              </li>
            ))}
            {ai.length === 0 && <li className="text-muted-foreground">{t('admin.no_ai_calls')}</li>}
          </ul>
        </section>
      </div>
    </div>
  )
}

/** Admin-only (the API answers 403 to anyone else). Account metadata only, never user content. */
export function AdminUsersPage() {
  const { t, locale } = useI18n()
  const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(locale) : '—')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(0)
  const users = useAdminUsers(q, page)
  const setBlocked = useSetBlocked()
  const me = useAuthUser()?.email?.toLowerCase()
  const total = users.data?.total ?? 0
  return (
    <Page title={t('admin.title')} description={t('admin.users.description')} wide>
      <AdminTabs />
      <Overview />
      <h2 className="text-sm font-semibold">{t('admin.users')}</h2>
      <Input
        aria-label={t('admin.search_aria')}
        placeholder={t('admin.search_ph')}
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setPage(0)
        }}
        className="max-w-sm"
      />
      {users.isPending && <ListSkeleton rows={4} />}
      <ErrorMessage error={users.error} />
      <ErrorMessage error={setBlocked.error} />
      {users.data && (
        <>
          <div className="overflow-x-auto rounded-xl border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="p-3 font-medium">{t('admin.col.email')}</th>
                  <th className="p-3 font-medium">{t('admin.col.name')}</th>
                  <th className="p-3 font-medium">{t('admin.col.joined')}</th>
                  <th className="p-3 font-medium">{t('admin.col.last_active')}</th>
                  <th className="p-3 font-medium">{t('admin.col.status')}</th>
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
                        <span className="text-destructive">{t('admin.blocked')}</span>
                      ) : (
                        <span className="text-muted-foreground">{t('admin.active')}</span>
                      )}
                    </td>
                    <td className="p-3 text-right">
                      {u.email.toLowerCase() !== me &&
                        (u.blocked ? (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={setBlocked.isPending}
                            aria-label={t('admin.unblock_aria', { email: u.email })}
                            onClick={() => setBlocked.mutate({ id: u.id, blocked: false })}
                          >
                            {t('admin.unblock')}
                          </Button>
                        ) : (
                          <ConfirmButton
                            label={t('admin.block')}
                            aria-label={t('admin.block_aria', { email: u.email })}
                            confirmLabel={t('admin.confirm_block')}
                            confirmAriaLabel={t('admin.confirm_block_aria', { email: u.email })}
                            pending={setBlocked.isPending}
                            onConfirm={(reset) =>
                              setBlocked.mutate({ id: u.id, blocked: true }, { onSettled: reset })
                            }
                          />
                        ))}
                    </td>
                  </tr>
                ))}
                {users.data.items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="p-6 text-center text-muted-foreground">
                      {t('admin.no_users')}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>{t('admin.user_count', { count: total })}</span>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                {t('admin.previous')}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={(page + 1) * PAGE >= total}
                onClick={() => setPage(page + 1)}
              >
                {t('admin.next')}
              </Button>
            </div>
          </div>
        </>
      )}
    </Page>
  )
}
