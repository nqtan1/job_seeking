import { ChevronsUpDown, CreditCard, LogOut, Monitor, Moon, Settings, Sun } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useT, type Key } from '@/i18n'
import { useMe } from '@/features/settings/api'
import { signOut, useAuthUser } from '@/lib/auth'
import { useTheme, type Theme } from '@/lib/theme'
import { cn } from 'cn'

const THEMES: [Theme, Key, typeof Sun][] = [
  ['system', 'app.theme_system', Monitor],
  ['light', 'app.theme_light', Sun],
  ['dark', 'app.theme_dark', Moon],
]

const item =
  'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-sidebar-accent'

/** The account row at the bottom of the left column; its menu opens upwards. */
export function AccountMenu({ collapsed }: { collapsed: boolean }) {
  const t = useT()
  const email = useAuthUser()?.email ?? t('app.account')
  const isAdmin = useMe().data?.is_admin
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useTheme()
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (
        e instanceof KeyboardEvent ? e.key === 'Escape' : !root.current?.contains(e.target as Node)
      )
        setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])

  return (
    <div ref={root} className="relative">
      {open && (
        <div
          role="menu"
          className="absolute right-0 bottom-full left-0 z-50 mb-2 min-w-56 space-y-1 rounded-xl border bg-popover p-1.5 text-popover-foreground shadow-lg"
        >
          <p className="truncate px-2 py-1 text-xs text-muted-foreground">{email}</p>
          <p
            role="menuitem"
            aria-disabled
            className={cn(item, 'cursor-default opacity-60 hover:bg-transparent')}
          >
            <CreditCard className="size-4" /> {t('app.plan')}
            <span className="ml-auto text-xs text-muted-foreground">{t('app.soon')}</span>
          </p>
          <Link role="menuitem" to="/settings" className={item} onClick={() => setOpen(false)}>
            <Settings className="size-4" /> {t('app.settings')}
          </Link>
          <div
            role="group"
            aria-label={t('app.theme')}
            className="flex gap-1 rounded-md bg-muted p-1"
          >
            {THEMES.map(([value, key, Icon]) => (
              <button
                key={value}
                aria-pressed={theme === value}
                aria-label={t(key)}
                title={t(key)}
                onClick={() => setTheme(value)}
                className={cn(
                  'grid flex-1 place-items-center rounded py-1',
                  theme === value ? 'bg-background shadow-xs' : 'text-muted-foreground',
                )}
              >
                <Icon className="size-4" />
              </button>
            ))}
          </div>
          <button role="menuitem" className={item} onClick={() => signOut()}>
            <LogOut className="size-4" /> {t('app.sign_out')}
          </button>
        </div>
      )}
      <button
        aria-label={t('app.account_menu')}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 rounded-lg p-2 text-left hover:bg-sidebar-accent"
      >
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground uppercase">
          {email[0]}
        </span>
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm">{email}</span>
              {isAdmin && (
                <span className="block text-xs text-muted-foreground">{t('app.admin_badge')}</span>
              )}
            </span>
            <ChevronsUpDown className="size-4 text-muted-foreground" />
          </>
        )}
      </button>
    </div>
  )
}
