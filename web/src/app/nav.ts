import { Bot, History, House, Workflow, Wrench, type LucideIcon } from 'lucide-react'
import { SCREENS, type Tab } from '@/features/tools/screens'

type Flags = { helpers_enabled?: boolean; cv_review_enabled?: boolean } | undefined
type Node = Tab & { tabs?: Tab[]; screens?: Node[] }
type Place = Node & { icon: LucideIcon }

/** The five places of the app. `screens` are pages reached from a place (it stays the active one
 *  there); `label` is a message key. */
const HOME: Place = { to: '/', label: 'nav.today', icon: House }
const TOOLS: Place = { to: '/tools', label: 'nav.tools', icon: Wrench, screens: SCREENS }
const AGENTS: Place[] = [
  // Coach is the first agent: its chat keeps /chat.
  {
    to: '/helpers',
    label: 'nav.agents',
    icon: Bot,
    screens: [{ to: '/chat', label: 'nav.coach' }],
  },
  { to: '/automations', label: 'nav.flows', icon: Workflow },
  { to: '/activity', label: 'nav.activity', icon: History },
]

const under = (path: string, to: string) =>
  to === '/' ? path === '/' : path === to || path.startsWith(`${to}/`)

/** Is `path` inside this place (itself, one of its tabs, or one of its screens)? A run page lives
 *  under /automations but belongs to Activity. */
export const inPlace = (p: Node, path: string): boolean =>
  under(path, '/automations/runs')
    ? p.to === '/activity'
    : under(path, p.to) ||
      !!p.tabs?.some((t) => under(path, t.to)) ||
      !!p.screens?.some((s) => inPlace(s, path))

/** The places this account may see (feature flags come from `/me`). */
export const navFor = (me: Flags) => [HOME, TOOLS, ...(me?.helpers_enabled ? AGENTS : [])]

/** The tab row of the career page holding `path` (Review only when CV review is on). */
export const tabsFor = (me: Flags, path: string) =>
  SCREENS.find((s) => inPlace(s, path))?.tabs?.filter(
    (t) => t.to !== '/cv-review' || me?.cv_review_enabled,
  )
