import { Bot, History, House, Search, type LucideIcon } from 'lucide-react'
import { SCREENS, type Tab } from '@/features/tools/screens'

type Flags = { helpers_enabled?: boolean; cv_review_enabled?: boolean } | undefined
type Node = Tab & { tabs?: Tab[]; screens?: Node[] }
type Place = Node & { icon: LucideIcon }

/** The places of the app. `screens` are pages reached from a place (it stays the active one
 *  there); `tabs` are shown as a tab row; `label` is a message key. */
// Home is the assistant: its chat keeps /chat.
const HOME: Place = {
  to: '/',
  label: 'nav.today',
  icon: House,
  screens: [{ to: '/chat', label: 'nav.coach' }],
}
const SEARCH: Place = { to: '/tools', label: 'nav.search', icon: Search, screens: SCREENS }
const STUDIO: Place = {
  to: '/helpers',
  label: 'nav.studio',
  icon: Bot,
  tabs: [
    { to: '/helpers', label: 'nav.agents' },
    { to: '/automations', label: 'nav.flows' },
    { to: '/agent-tools', label: 'nav.tools' },
  ],
}
const ACTIVITY: Place = { to: '/activity', label: 'nav.activity', icon: History }

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
export const navFor = (me: Flags) => [
  HOME,
  SEARCH,
  ...(me?.helpers_enabled ? [ACTIVITY, STUDIO] : []),
]

/** The tab row of the page holding `path` (Review only when CV review is on). */
export const tabsFor = (me: Flags, path: string) =>
  [...SCREENS, STUDIO]
    .find((s) => inPlace(s, path))
    ?.tabs?.filter((t) => t.to !== '/cv-review' || me?.cv_review_enabled)
