import {
  Briefcase,
  FileSearch,
  Gauge,
  Globe,
  Kanban,
  Mail,
  Radar,
  Search,
  Send,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Input } from '@/components/ui/input'
import { type Key, catalogs, useT } from '@/i18n'
import { type Tool, toolText, useTools } from './api'
import { SCREENS } from './screens'

/** Packs in menu order; "core" (for_each, wait) is flow plumbing and never shown here. */
const PACKS = ['career', 'web', 'messages']
const ICON: Record<string, LucideIcon> = {
  web_search: Globe,
  job_search: Search,
  find_offers: Radar,
  fit_check: Gauge,
  read_page: FileSearch,
  job_lookup: Briefcase,
  add_to_tracker: Kanban,
  send_email: Mail,
  telegram_send: Send,
}

const norm = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()

type CardData = {
  key: string
  to: string
  name: string
  line: string
  icon: LucideIcon
  chips: string[]
}

function ToolCard({ c }: { c: CardData }) {
  return (
    <li>
      <Link
        to={c.to}
        className="flex h-full items-start gap-3 rounded-xl border bg-card p-4 shadow-xs transition-colors outline-none hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <c.icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
        <span className="min-w-0 flex-1 space-y-1">
          <span className="block font-medium">{c.name}</span>
          {c.line && <span className="block truncate text-sm text-muted-foreground">{c.line}</span>}
          {c.chips.length > 0 && (
            <span className="flex flex-wrap gap-1">
              {c.chips.map((chip) => (
                <span key={chip} className="rounded bg-muted px-1.5 text-xs leading-5">
                  {chip}
                </span>
              ))}
            </span>
          )}
        </span>
      </Link>
    </li>
  )
}

export function ToolsPage() {
  const t = useT()
  const tools = useTools()
  const [q, setQ] = useState('')
  const card = (tool: Tool): CardData => ({
    key: tool.id,
    to: tool.page ?? `/tools/${tool.id}`,
    name: toolText(t, tool.id, 'name'),
    line: toolText(t, tool.id, 'short'),
    icon: ICON[tool.id] ?? Wrench,
    chips: [
      ...(tool.ai_uses > 0 ? [t('tools.ai')] : []),
      ...(tool.daily_cap ? [t('tools.cap', { count: tool.daily_cap })] : []),
      ...(tool.effect === 'outside' ? [t('tools.outside')] : []),
    ],
  })
  const screens: CardData[] = SCREENS.map((s) => ({
    key: s.to,
    to: s.to,
    name: t(s.label),
    line: t(s.desc),
    icon: s.icon,
    chips: [],
  }))
  // core = flow plumbing; a tool with its own page is reached through that page's card
  const shown = (tools.data ?? []).filter((x) => x.pack !== 'core' && !x.page)
  const packs = [...new Set([...PACKS, ...shown.map((x) => x.pack)])]
  const sections = packs
    .map((pack) => ({
      pack,
      cards: [
        ...(pack === 'career' ? screens : []),
        ...shown.filter((x) => x.pack === pack).map(card),
      ].filter((c) => norm(c.name).includes(norm(q.trim()))),
    }))
    .filter((s) => s.cards.length > 0)
  return (
    <Page title={t('nav.tools')}>
      <Input
        type="search"
        aria-label={t('tools.search')}
        placeholder={t('tools.search')}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="max-w-sm"
      />
      <ErrorMessage error={tools.error} />
      {sections.map(({ pack, cards }) => (
        <section key={pack} aria-labelledby={`pack-${pack}`} className="space-y-3">
          <h2 id={`pack-${pack}`} className="text-sm font-medium text-muted-foreground">
            {`tools.pack.${pack}` in catalogs.en ? t(`tools.pack.${pack}` as Key) : pack}
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {cards.map((c) => (
              <ToolCard key={c.key} c={c} />
            ))}
          </ul>
        </section>
      ))}
      {tools.isLoading && <ListSkeleton />}
      {sections.length === 0 && <EmptyState icon={Search} title={t('tools.none')} />}
    </Page>
  )
}
