import { LayoutDashboard, MessageSquare, PanelLeft, Sparkles, SquarePen } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router'
import { useT } from '@/i18n'
import { useConversations } from '@/features/coach/api'
import { useLetters } from '@/features/letters/api'
import { RadarBadge } from '@/features/radar/RadarBadge'
import { useMe } from '@/features/settings/api'
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

function Recent() {
  const t = useT()
  const chats = useConversations().data?.slice(0, 8) ?? []
  const letters = useLetters().data?.slice(0, 5) ?? []
  if (chats.length + letters.length === 0) return null
  const heading = 'px-2 pt-3 pb-1 text-xs font-medium text-muted-foreground'
  return (
    <>
      {chats.length > 0 && (
        <section aria-label={t('nav.recent_chats')}>
          <p className={heading}>{t('nav.chats')}</p>
          {chats.map((c) => (
            <NavLink key={c.id} to={`/chat/${c.id}`} className={active}>
              <MessageSquare className="size-4 shrink-0 opacity-60" />
              <span className="truncate">{c.title ?? t('nav.new_chat')}</span>
            </NavLink>
          ))}
        </section>
      )}
      {letters.length > 0 && (
        <section aria-label={t('nav.recent_letters')}>
          <p className={heading}>{t('nav.letters')}</p>
          {letters.map((l) => (
            <NavLink key={l.id} to={`/letters/${l.id}`} className={active}>
              <span className="truncate pl-6">{l.content.subject || t('nav.untitled_letter')}</span>
            </NavLink>
          ))}
        </section>
      )}
    </>
  )
}

/** The left column: new chat, tools, recent items, account. Shared by desktop and the mobile drawer. */
export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle?: () => void }) {
  const t = useT()
  const isAdmin = useMe().data?.is_admin
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
      <AccountMenu collapsed={collapsed} />
    </div>
  )
}
