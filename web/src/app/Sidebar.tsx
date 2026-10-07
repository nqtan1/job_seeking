import { LayoutDashboard, MessageSquare, PanelLeft, Sparkles, SquarePen } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router'
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
  const chats = useConversations().data?.slice(0, 8) ?? []
  const letters = useLetters().data?.slice(0, 5) ?? []
  if (chats.length + letters.length === 0) return null
  const heading = 'px-2 pt-3 pb-1 text-xs font-medium text-muted-foreground'
  return (
    <>
      {chats.length > 0 && (
        <section aria-label="Recent chats">
          <p className={heading}>Chats</p>
          {chats.map((c) => (
            <NavLink key={c.id} to={`/chat/${c.id}`} className={active}>
              <MessageSquare className="size-4 shrink-0 opacity-60" />
              <span className="truncate">{c.title ?? 'New chat'}</span>
            </NavLink>
          ))}
        </section>
      )}
      {letters.length > 0 && (
        <section aria-label="Recent letters">
          <p className={heading}>Letters</p>
          {letters.map((l) => (
            <NavLink key={l.id} to={`/letters/${l.id}`} className={active}>
              <span className="truncate pl-6">{l.content.subject || 'Untitled letter'}</span>
            </NavLink>
          ))}
        </section>
      )}
    </>
  )
}

/** The left column: new chat, tools, recent items, account. Shared by desktop and the mobile drawer. */
export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle?: () => void }) {
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
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            onClick={onToggle}
            className="grid size-8 place-items-center rounded-lg text-muted-foreground hover:bg-sidebar-accent"
          >
            <PanelLeft className="size-4" />
          </button>
        )}
      </div>
      <NavLink to="/" end className={active} title="New chat">
        <SquarePen className="size-4 shrink-0" />
        <Label collapsed={collapsed}>New chat</Label>
      </NavLink>
      <nav aria-label="Main" className="space-y-0.5 pt-2">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} className={active} title={label}>
            <Icon className="size-4 shrink-0" />
            <Label collapsed={collapsed}>{label}</Label>
            {to === '/radar' && <RadarBadge collapsed={collapsed} />}
          </NavLink>
        ))}
        {isAdmin && (
          <NavLink to="/admin" className={active} title="Admin">
            <LayoutDashboard className="size-4 shrink-0" />
            <Label collapsed={collapsed}>Admin</Label>
          </NavLink>
        )}
      </nav>
      {/* Always takes the free height, so the account row stays at the very bottom. */}
      <div className="min-h-0 flex-1 overflow-y-auto">{!collapsed && <Recent />}</div>
      <AccountMenu collapsed={collapsed} />
    </div>
  )
}
