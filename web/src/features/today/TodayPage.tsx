import { ArrowRight, Bell, Check, FileText, MessageSquare, ScanSearch, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { ListSkeleton } from '@/components/Skeleton'
import { buttonVariants } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { cn } from 'cn'
import { useToday } from './steps'

const KIND = { chat: MessageSquare, letter: FileText, review: ScanSearch }
const DOT: Record<string, string> = {
  done: 'bg-success',
  failed: 'bg-destructive',
  cancelled: 'bg-muted-foreground',
}
const row = 'flex items-center gap-3 rounded-lg px-2 py-2 text-sm hover:bg-accent'

/** Reminders closed today stay closed until tomorrow (this device only). */
const DAY = new Date().toDateString()
function readClosed(): string[] {
  try {
    const saved = JSON.parse(localStorage.getItem('home-closed') ?? '{}')
    return saved.day === DAY ? saved.keys : []
  } catch {
    return []
  }
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="space-y-1">
      <h2 className="px-2 text-sm font-medium text-muted-foreground">{title}</h2>
      {children}
    </section>
  )
}

/** Home: a dashboard. What needs you (reminders), where you stand (numbers), what your flows did,
 *  what you touched last. Every row opens the page that does the real work. */
export function TodayPage() {
  const { t, locale } = useI18n()
  const { loading, steps, todo, reminders, stats, runs, recent } = useToday()
  const [closed, setClosed] = useState(readClosed)
  const close = (key: string) => {
    const keys = [...closed, key]
    setClosed(keys)
    try {
      localStorage.setItem('home-closed', JSON.stringify({ day: DAY, keys }))
    } catch {
      /* closed for this visit only */
    }
  }
  const done = steps.filter((s) => s.done).length
  const day = (iso: string) =>
    new Date(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short' })
  const open = reminders.filter((r) => !closed.includes(r.key))

  return (
    <div className="mx-auto w-full max-w-4xl space-y-8 p-6 md:p-10">
      <h1 className="text-3xl font-semibold tracking-tight">{t('today.title')}</h1>
      {loading ? (
        <ListSkeleton rows={4} />
      ) : (
        <>
          {open.length > 0 && (
            <ul aria-label={t('today.reminders')} className="space-y-2">
              {open.map((r) => (
                <li
                  key={r.key}
                  className="flex items-center gap-3 rounded-2xl border border-primary/30 bg-primary/5 p-3 pl-4"
                >
                  <Bell className="size-4 shrink-0 text-primary" />
                  <Link to={r.to} className="min-w-0 flex-1 font-medium hover:underline">
                    {t(r.label, { count: r.count })}
                  </Link>
                  <button
                    type="button"
                    aria-label={t('today.close')}
                    onClick={() => close(r.key)}
                    className="grid size-8 place-items-center rounded-lg text-muted-foreground hover:bg-accent"
                  >
                    <X className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <ul className="grid grid-cols-3 gap-3">
            {stats.map((s) => (
              <li key={s.label}>
                <Link
                  to={s.to}
                  className="block rounded-2xl border bg-card p-4 transition-colors hover:bg-accent"
                >
                  <span className="block text-3xl font-semibold tabular-nums">{s.value}</span>
                  <span className="text-sm text-muted-foreground">{t(s.label)}</span>
                </Link>
              </li>
            ))}
          </ul>

          {todo && (
            <section
              aria-label={t('today.next')}
              className="space-y-4 rounded-2xl border bg-card p-6 shadow-xs"
            >
              <div className="flex flex-wrap items-center gap-4">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-muted-foreground">
                    {t('today.next')} · {done}/{steps.length}
                  </p>
                  <p className="text-xl font-semibold tracking-tight">{t(todo.label)}</p>
                </div>
                <Link to={todo.to} className={buttonVariants()}>
                  {t('today.go')} <ArrowRight />
                </Link>
              </div>
              <ol className="flex gap-1.5" aria-hidden>
                {steps.map((s) => (
                  <li
                    key={s.label}
                    className={cn('h-1.5 flex-1 rounded-full', s.done ? 'bg-primary' : 'bg-muted')}
                  />
                ))}
              </ol>
            </section>
          )}

          <div className="grid gap-8 md:grid-cols-2">
            {runs.length > 0 && (
              <Section title={t('today.flows')}>
                <ul>
                  {runs.map((r) => (
                    <li key={r.id}>
                      <Link to={`/automations/runs/${r.id}`} className={row}>
                        <span
                          className={cn(
                            'size-2 shrink-0 rounded-full',
                            DOT[r.status] ?? 'animate-pulse bg-primary',
                          )}
                        />
                        <span className="min-w-0 flex-1 truncate">{r.flow_name}</span>
                        <span className="text-xs text-muted-foreground">{day(r.created_at)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {recent.length > 0 && (
              <Section title={t('today.recent')}>
                <ul>
                  {recent.map((it) => {
                    const Icon = KIND[it.kind]
                    return (
                      <li key={it.key}>
                        <Link to={it.to} className={row}>
                          <Icon className="size-4 shrink-0 text-muted-foreground" />
                          <span className="min-w-0 flex-1 truncate">
                            {it.text || t(`today.kind.${it.kind}`)}
                          </span>
                          <span className="text-xs text-muted-foreground">{day(it.at)}</span>
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              </Section>
            )}
          </div>
          {!todo && open.length === 0 && runs.length === 0 && recent.length === 0 && (
            <p className="flex items-center gap-2 text-muted-foreground">
              <Check className="size-4 text-success" /> {t('today.clear')}
            </p>
          )}
        </>
      )}
    </div>
  )
}
