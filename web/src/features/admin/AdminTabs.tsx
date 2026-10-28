import { NavLink } from 'react-router'
import { cn } from 'cn'
import { useT, type Key } from '@/i18n'

const TABS = [
  { to: '/admin', label: 'admin.tab.overview' as Key, end: true },
  { to: '/admin/ai', label: 'admin.tab.ai' as Key, end: false },
]

/** The admin area's two screens. */
export function AdminTabs() {
  const t = useT()
  return (
    <nav aria-label={t('admin.tabs_aria')} className="flex gap-1 border-b">
      {TABS.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          end={l.end}
          className={({ isActive }) =>
            cn(
              '-mb-px border-b-2 px-3 py-1.5 text-sm',
              isActive ? 'border-primary font-medium' : 'border-transparent text-muted-foreground',
            )
          }
        >
          {t(l.label)}
        </NavLink>
      ))}
    </nav>
  )
}
