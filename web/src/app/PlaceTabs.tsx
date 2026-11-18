import { Link, NavLink, useLocation } from 'react-router'
import { RadarBadge } from '@/features/radar/RadarBadge'
import { useMe } from '@/features/settings/api'
import { useT } from '@/i18n'
import { cn } from 'cn'
import { inPlace, navFor, tabsFor } from './nav'

/** The screens of the current page, as a tab row above it (nothing for a one-screen page). */
export function PlaceTabs() {
  const t = useT()
  const { pathname } = useLocation()
  const tabs = tabsFor(useMe().data, pathname)
  if (!tabs || tabs.length < 2) return null
  return (
    <nav aria-label={t('nav.section')} className="flex shrink-0 gap-1 border-b px-4 pt-2 md:px-6">
      {tabs.map(({ to, label }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            cn(
              '-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm transition-colors',
              isActive
                ? 'border-primary font-medium'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )
          }
        >
          {t(label)}
          {to === '/radar' && <RadarBadge />}
        </NavLink>
      ))}
    </nav>
  )
}

/** Phone only: the places one thumb away (the drawer keeps the rest). */
export function BottomTabs() {
  const t = useT()
  const { pathname } = useLocation()
  return (
    <nav
      aria-label={t('nav.places')}
      className="flex shrink-0 border-t bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      {navFor(useMe().data).map((p) => {
        const on = inPlace(p, pathname)
        return (
          <Link
            key={p.to}
            to={p.to}
            aria-current={on ? 'page' : undefined}
            className={cn(
              'flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[11px]',
              on ? 'font-medium text-primary' : 'text-muted-foreground',
            )}
          >
            <p.icon className="size-5" />
            {t(p.label)}
          </Link>
        )
      })}
    </nav>
  )
}
