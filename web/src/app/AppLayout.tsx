import { Menu } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Outlet } from 'react-router'
import { Toaster } from '@/components/Toaster'
import { SessionGuard } from '@/features/auth/SessionGuard'
import { useMe } from '@/features/settings/api'
import { setLang, useT } from '@/i18n'
import { useRadarTitle } from '@/features/radar/useRadarTitle'
import { cn } from 'cn'
import { ColdStartNotice } from './ColdStartNotice'
import { Sidebar } from './Sidebar'

const KEY = 'sidebar-collapsed'
const readCollapsed = () => {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

/** ChatGPT/Claude-style shell: the left column holds the tools and the account; the main area
 *  takes the rest. On small screens the column is a drawer. */
export function AppLayout() {
  const t = useT()
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const [drawer, setDrawer] = useState(false)
  useRadarTitle()
  // The account's language wins over this device's guess, on every sign-in.
  const language = useMe().data?.language
  useEffect(() => {
    if (language) setLang(language)
  }, [language])

  useEffect(() => {
    try {
      localStorage.setItem(KEY, collapsed ? '1' : '0')
    } catch {
      /* the choice then lasts for the session only */
    }
  }, [collapsed])

  return (
    <div className="flex h-dvh bg-background">
      <SessionGuard />
      <aside
        className={cn(
          'hidden shrink-0 border-r bg-sidebar text-sidebar-foreground transition-[width] duration-200 md:block',
          collapsed ? 'w-14' : 'w-64',
        )}
      >
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      </aside>

      {drawer && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setDrawer(false)} />
          <aside
            onClick={(e) => (e.target as HTMLElement).closest('a') && setDrawer(false)}
            className="relative h-full w-72 max-w-[85vw] border-r bg-sidebar text-sidebar-foreground shadow-xl"
          >
            <Sidebar collapsed={false} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center gap-2 border-b px-3 md:hidden">
          <button
            aria-label={t('nav.open_menu')}
            onClick={() => setDrawer(true)}
            className="grid size-8 place-items-center rounded-lg hover:bg-muted"
          >
            <Menu className="size-5" />
          </button>
          <span className="font-semibold">RecruitAI</span>
        </div>
        <ColdStartNotice />
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <Toaster />
    </div>
  )
}
