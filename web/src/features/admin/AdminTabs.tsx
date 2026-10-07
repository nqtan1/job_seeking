import { NavLink } from 'react-router'
import { cn } from 'cn'

const TABS = [
  { to: '/admin', label: 'Overview', end: true },
  { to: '/admin/ai', label: 'AI console', end: false },
]

/** The admin area's two screens. */
export function AdminTabs() {
  return (
    <nav aria-label="Admin sections" className="flex gap-1 border-b">
      {TABS.map((t) => (
        <NavLink
          key={t.to}
          to={t.to}
          end={t.end}
          className={({ isActive }) =>
            cn(
              '-mb-px border-b-2 px-3 py-1.5 text-sm',
              isActive ? 'border-primary font-medium' : 'border-transparent text-muted-foreground',
            )
          }
        >
          {t.label}
        </NavLink>
      ))}
    </nav>
  )
}
