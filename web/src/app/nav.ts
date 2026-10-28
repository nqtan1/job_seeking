import { Briefcase, FileText, Kanban, Radar, UserRound, type LucideIcon } from 'lucide-react'
import type { Key } from '@/i18n'

/** `label` is a message key: translate at render. */
export const NAV: { to: string; label: Key; icon: LucideIcon }[] = [
  { to: '/profile', label: 'nav.profile', icon: UserRound },
  { to: '/jobs', label: 'nav.jobs', icon: Briefcase },
  { to: '/radar', label: 'nav.radar', icon: Radar },
  { to: '/letters', label: 'nav.letters', icon: FileText },
  { to: '/tracker', label: 'nav.tracker', icon: Kanban },
]
