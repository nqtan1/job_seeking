import { Briefcase, FileText, Kanban, type LucideIcon } from 'lucide-react'
import type { Key } from '@/i18n'

export type Tab = { to: string; label: Key }
export type Screen = Tab & { icon: LucideIcon; desc: Key; tabs?: Tab[] }

/** The career pages: cards in Tools (they are pages, not registry tools). `tabs` are the
 *  screens one page holds, shown as a tab row above it; every old URL still opens. */
export const SCREENS: Screen[] = [
  {
    to: '/jobs',
    label: 'nav.jobs',
    desc: 'tool.jobs.desc',
    icon: Briefcase,
    tabs: [
      { to: '/jobs', label: 'nav.saved' },
      { to: '/radar', label: 'nav.radar' },
    ],
  },
  { to: '/tracker', label: 'nav.applications', desc: 'tool.tracker.desc', icon: Kanban },
  {
    to: '/profile',
    label: 'nav.cv',
    desc: 'tool.cv.desc',
    icon: FileText,
    tabs: [
      { to: '/profile', label: 'nav.profile' },
      { to: '/cv-review', label: 'nav.review' },
      { to: '/letters', label: 'nav.letters' },
    ],
  },
]
