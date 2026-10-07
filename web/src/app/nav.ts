import { Briefcase, FileText, Kanban, Radar, UserRound, type LucideIcon } from 'lucide-react'

export const NAV: { to: string; label: string; icon: LucideIcon }[] = [
  { to: '/profile', label: 'Profile', icon: UserRound },
  { to: '/jobs', label: 'Jobs', icon: Briefcase },
  { to: '/radar', label: 'Radar', icon: Radar },
  { to: '/letters', label: 'Letters', icon: FileText },
  { to: '/tracker', label: 'Tracker', icon: Kanban },
]
