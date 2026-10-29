import {
  FileText,
  LayoutDashboard,
  MessageSquare,
  PanelLeft,
  Sparkles,
  SquarePen,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router'
import { LanguageSelect } from '@/components/LanguageSelect'
import { useT } from '@/i18n'
import { useConversations } from '@/features/coach/api'
import { useJobs } from '@/features/job-search/api'
import { useLetters } from '@/features/letters/api'
import { RadarBadge } from '@/features/radar/RadarBadge'
import { useMe, useSetLanguage } from '@/features/settings/api'
import { cn } from 'cn'
import { AccountMenu } from './AccountMenu'
import { NAV } from './nav'

const row = 'flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors'
const active = ({ isActive }: { isActive: boolean }) =>
  cn(
    row,
    isActive
      ? 'bg-sidebar-accent font-medium text-sidebar-accent-foreground'
      : 'hover:bg-sidebar-accent/60',
  )

function Label({ collapsed, children }: { collapsed: boolean; children: ReactNode }) {
  return <span className={cn('truncate', collapsed && 'sr-only')}>{children}</span>
}

const norm = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim()

/** Same employer, same hue. The text mixes with currentColor so it stays readable in dark mode. */
function CompanyChip({ name }: { name: string }) {
  let h = 0
  for (const ch of norm(name)) h = (h * 31 + ch.charCodeAt(0)) % 360
  return (
    <span
      className="max-w-24 shrink-0 truncate rounded px-1.5 text-[10px] leading-4"
      style={{
        background: `hsl(${h} 70% 50% / 0.15)`,
        color: `color-mix(in oklab, hsl(${h} 70% 50%) 60%, currentColor)`,
      }}
    >
      {name}
    </span>
  )
}

type Item = { key: string; to: string; label: string; at: number; company?: string; chat: boolean }
const DAYS = ['day_today', 'day_yesterday', 'day_week', 'day_earlier'] as const

/** Local calendar-day bucket: 0 today, 1 yesterday, 2 within 7 days, 3 earlier. */
function bucket(at: number, now = new Date()) {
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const diff = Math.round((day(now) - day(new Date(at))) / 864e5)
  return diff <= 0 ? 0 : diff === 1 ? 1 : diff < 7 ? 2 : 3
}

function Recent() {
  const t = useT()
  const chats = useConversations().data?.slice(0, 8)
  const letters = useLetters().data?.slice(0, 5)
  const jobs = useJobs().data
  // Company comes from the cached jobs list: no extra request per item.
  const companyFor = (id: string | null) => {
    const j = id ? jobs?.find((x) => x.id === id) : undefined
    return j?.data.company.name?.trim() || undefined
  }
  const items: Item[] = [
    ...(chats ?? []).map((c) => ({
      key: `c${c.id}`,
      to: `/chat/${c.id}`,
      label: c.title ?? t('nav.new_chat'),
      at: Date.parse(c.updated_at),
      company: companyFor(c.job_id),
      chat: true,
    })),
    ...(letters ?? []).map((l) => ({
      key: `l${l.id}`,
      to: `/letters/${l.id}`,
      label: l.content.subject || t('nav.untitled_letter'),
      at: Date.parse(l.updated_at),
      company: companyFor(l.job_id),
      chat: false,
    })),
  ].sort((a, b) => b.at - a.at)
  if (items.length === 0) return null
  return (
    <nav aria-label={t('nav.recent')}>
      {DAYS.map((d, i) => {
        const group = items.filter((it) => bucket(it.at) === i)
        if (group.length === 0) return null
        return (
          <section key={d} aria-label={t(`nav.${d}`)}>
            <p className="px-2 pt-3 pb-1 text-xs font-medium text-muted-foreground">
              {t(`nav.${d}`)}
            </p>
            {group.map((it) => (
              <NavLink key={it.key} to={it.to} className={active}>
                {it.chat ? (
                  <MessageSquare className="size-4 shrink-0 opacity-60" />
                ) : (
                  <FileText className="size-4 shrink-0 opacity-60" />
                )}
                <span className="min-w-0 flex-1 truncate">{it.label}</span>
                {it.company && <CompanyChip name={it.company} />}
              </NavLink>
            ))}
          </section>
        )
      })}
    </nav>
  )
}

/** The left column: new chat, tools, recent items, account. Shared by desktop and the mobile drawer. */
export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle?: () => void }) {
  const t = useT()
  const isAdmin = useMe().data?.is_admin
  const setLanguage = useSetLanguage()
  return (
    <div className="flex h-full flex-col gap-1 p-2">
      <div className="flex items-center justify-between gap-2 px-1 pb-2">
        <Link to="/" className="flex items-center gap-2 font-semibold">
          <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground">
            <Sparkles className="size-4" />
          </span>
          <Label collapsed={collapsed}>RecruitAI</Label>
        </Link>
        {onToggle && (
          <button
            aria-label={collapsed ? t('nav.expand') : t('nav.collapse')}
            onClick={onToggle}
            className="grid size-8 place-items-center rounded-lg text-muted-foreground hover:bg-sidebar-accent"
          >
            <PanelLeft className="size-4" />
          </button>
        )}
      </div>
      <NavLink to="/" end className={active} title={t('nav.new_chat')}>
        <SquarePen className="size-4 shrink-0" />
        <Label collapsed={collapsed}>{t('nav.new_chat')}</Label>
      </NavLink>
      <nav aria-label={t('nav.main')} className="space-y-0.5 pt-2">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} className={active} title={t(label)}>
            <Icon className="size-4 shrink-0" />
            <Label collapsed={collapsed}>{t(label)}</Label>
            {to === '/radar' && <RadarBadge collapsed={collapsed} />}
          </NavLink>
        ))}
        {isAdmin && (
          <NavLink to="/admin" className={active} title={t('nav.admin')}>
            <LayoutDashboard className="size-4 shrink-0" />
            <Label collapsed={collapsed}>{t('nav.admin')}</Label>
          </NavLink>
        )}
      </nav>
      {/* Always takes the free height, so the account row stays at the very bottom. */}
      <div className="min-h-0 flex-1 overflow-y-auto">{!collapsed && <Recent />}</div>
      {!collapsed && (
        <div className="px-1 pb-1">
          <LanguageSelect id="sidebar-language" onChange={(l) => setLanguage.mutate(l)} />
        </div>
      )}
      <AccountMenu collapsed={collapsed} />
    </div>
  )
}
