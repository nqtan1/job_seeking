import {
  ArrowRight,
  Bell,
  Check,
  FileText,
  MessageSquare,
  ScanSearch,
  SendHorizontal,
  X,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'
import { ListSkeleton } from '@/components/Skeleton'
import { Button, buttonVariants } from '@/components/ui/button'
import { INBOX_KIND, appPath } from '@/features/coach/actions'
import { MAX_MESSAGE } from '@/features/coach/link'
import { useI18n, useT } from '@/i18n'
import { relTime } from '@/lib/time'
import { cn } from 'cn'
import { useInbox, useToday } from './steps'

const KIND = { chat: MessageSquare, letter: FileText, review: ScanSearch }
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

/** A row's time, the same style everywhere on Home ("3 hours ago"). */
function Ago({ iso, now }: { iso: string; now: number }) {
  const { locale } = useI18n()
  return (
    <time dateTime={iso} className="shrink-0 text-xs text-muted-foreground">
      {relTime(iso, locale, now)}
    </time>
  )
}

/** Home is the assistant: ask it, what needs you, what it did (inbox), the next onboarding step,
 *  where you stand, what you touched last. Every row opens the page that does the real work. */
export function TodayPage() {
  const t = useT()
  const { loading, profile, steps, todo, reminders, stats, recent } = useToday()
  const inbox = useInbox()
  const [now] = useState(Date.now) // once per visit: render stays pure
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
  const open = reminders.filter((r) => !closed.includes(r.key))

  return (
    <div className="mx-auto w-full max-w-4xl space-y-8 p-6 md:p-10">
      <h1 className="text-3xl font-semibold tracking-tight">{t('today.title')}</h1>
      {loading ? (
        <ListSkeleton rows={4} />
      ) : (
        <>
          {profile && <Ask />}
          <Reminders open={open} close={close} />
          <Inbox inbox={inbox} now={now} />
          {todo && <NextStep todo={todo} steps={steps} />}
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
          <Recent recent={recent} now={now} />
          {!todo && open.length === 0 && !inbox.items.length && !recent.length && (
            <p className="flex items-center gap-2 text-muted-foreground">
              <Check className="size-4 text-success" /> {t('today.clear')}
            </p>
          )}
        </>
      )}
    </div>
  )
}

type Today = ReturnType<typeof useToday>

/** The ask box: a new chat with the question in it, sent at once. */
function Ask() {
  const t = useT()
  const navigate = useNavigate()
  const [text, setText] = useState('')
  return (
    <form
      aria-label={t('today.ask')}
      className="flex items-center gap-2 rounded-2xl border bg-card p-2 pl-4 shadow-xs focus-within:ring-3 focus-within:ring-ring/40"
      onSubmit={(e) => {
        e.preventDefault()
        if (text.trim()) navigate(`/chat?ask=${encodeURIComponent(text.trim())}`)
      }}
    >
      <input
        aria-label={t('today.ask')}
        placeholder={t('today.ask_hint')}
        value={text}
        maxLength={MAX_MESSAGE}
        onChange={(e) => setText(e.target.value)}
        className="min-w-0 flex-1 bg-transparent py-2 outline-none placeholder:text-muted-foreground"
      />
      <Button type="submit" size="icon" variant="ghost" aria-label={t('today.ask_send')}>
        <SendHorizontal />
      </Button>
    </form>
  )
}

/** The latest messages of the Assistant conversation: what ran or failed. */
function Inbox({ inbox, now }: { inbox: ReturnType<typeof useInbox>; now: number }) {
  const t = useT()
  if (!inbox.id || inbox.items.length === 0) return null
  const all = `/chat/${inbox.id}`
  return (
    <Section title={t('today.inbox')}>
      <ul>
        {inbox.items.map((m) => {
          const kind = INBOX_KIND[m.kind] ?? INBOX_KIND.reminder
          return (
            <li key={m.id}>
              <Link to={appPath(m.link) ?? all} className={row}>
                <kind.icon className={cn('size-4 shrink-0', kind.color)} aria-hidden />
                <span className="line-clamp-2 min-w-0 flex-1">{m.text}</span>
                <Ago iso={m.at} now={now} />
              </Link>
            </li>
          )
        })}
      </ul>
      <Link to={all} className={buttonVariants({ variant: 'link', size: 'sm' })}>
        {t('today.see_all')}
      </Link>
    </Section>
  )
}

function Reminders({ open, close }: { open: Today['reminders']; close: (key: string) => void }) {
  const t = useT()
  if (open.length === 0) return null
  return (
    <Section title={t('today.reminders')}>
      <ul className="space-y-2">
        {open.map((r) => (
          <li
            key={r.key}
            className="flex items-center gap-3 rounded-2xl border border-primary/30 bg-primary/5 p-3 pl-4"
          >
            <Bell className="size-4 shrink-0 text-primary" aria-hidden />
            <Link to={r.to} className="min-w-0 flex-1 font-medium hover:underline">
              {t(r.label, { count: r.count })}
            </Link>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label={t('today.close')}
              onClick={() => close(r.key)}
            >
              <X />
            </Button>
          </li>
        ))}
      </ul>
    </Section>
  )
}

function NextStep({ todo, steps }: { todo: NonNullable<Today['todo']>; steps: Today['steps'] }) {
  const t = useT()
  const done = steps.filter((s) => s.done).length
  return (
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
  )
}

function Recent({ recent, now }: { recent: Today['recent']; now: number }) {
  const t = useT()
  if (recent.length === 0) return null
  return (
    <Section title={t('today.recent')}>
      <ul>
        {recent.map((it) => {
          const Icon = KIND[it.kind]
          return (
            <li key={it.key}>
              <Link to={it.to} className={row}>
                <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0 flex-1 truncate">
                  {it.text || t(`today.kind.${it.kind}`)}
                </span>
                <Ago iso={it.at} now={now} />
              </Link>
            </li>
          )
        })}
      </ul>
    </Section>
  )
}
