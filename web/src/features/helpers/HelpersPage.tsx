import '@/features/helpers/lib'
import { ArrowRight, Briefcase, FileText, Plus, Sparkles, UserRound } from 'lucide-react'
import { useNavigate } from 'react-router'
import { cn } from 'cn'
import { type Key, useI18n, useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Spinner } from '@/components/Spinner'
import { Button } from '@/components/ui/button'
import { useAgents, useArchiveAgent, useCreateAgent } from './api'
import { Avatar } from './Avatar'
import { Hero, ItemCard, Trio } from './ui'
import { LIFT } from './lib'
import { PALETTES, avatarFromSeed } from './avatar'
import type { VersionSpec } from './graph'
import { BLANK_SPEC, STARTERS, type Starter, localized } from './starters'

export function HelpersPage() {
  const t = useT()
  return (
    <Page title={t('helpers.title')} description={t('helpers.subtitle')}>
      <Hero title={t('helpers.ui.hero_title')} body={t('helpers.ui.hero_body')} />
      <HelpersTab />
    </Page>
  )
}

function Chip({
  icon: Icon,
  label,
  hint,
}: {
  icon: typeof Briefcase
  label: string
  hint: string
}) {
  return (
    <li className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
      <Icon className="size-3" aria-hidden />
      <span className="sr-only">{hint}: </span>
      {label}
    </li>
  )
}

const SOURCE_CHIP = { profile: UserRound, job: Briefcase, fit: Sparkles } as const

function TemplateChips({ s }: { s: Starter }) {
  const t = useT()
  const reads: [typeof Briefcase, Key][] = [
    ...(s.spec.inputs?.length
      ? [[FileText, 'helpers.ui.chip.notes'] as [typeof Briefcase, Key]]
      : []),
    ...(s.spec.context_sources ?? []).map(
      (c) => [SOURCE_CHIP[c], `helpers.ui.chip.${c}` as Key] as [typeof Briefcase, Key],
    ),
  ]
  return (
    <ul className="flex flex-wrap gap-1.5">
      {reads.map(([icon, key]) => (
        <Chip key={key} icon={icon} label={t(key)} hint={t('helpers.ui.reads')} />
      ))}
      <li className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs text-accent-foreground">
        <ArrowRight className="size-3" aria-hidden />
        <span className="sr-only">{t('helpers.ui.gives')}: </span>
        {t(s.spec.output.kind === 'fields' ? 'helpers.ui.chip.fields' : 'helpers.ui.chip.text')}
      </li>
    </ul>
  )
}

function Tint({ palette, children }: { palette: number; children: React.ReactNode }) {
  const c = PALETTES[palette % PALETTES.length]?.accent ?? PALETTES[0].accent
  return (
    <span
      className="grid shrink-0 place-items-center rounded-2xl p-1.5"
      style={{ background: `color-mix(in oklab, ${c} 14%, transparent)` }}
    >
      {children}
    </span>
  )
}

function HelpersTab() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const agents = useAgents()
  const create = useCreateAgent()
  const archive = useArchiveAgent()

  const start = (name: string, description: string, spec: VersionSpec) =>
    create.mutate(
      { name, description, spec, note: '' },
      { onSuccess: (a) => navigate(`/helpers/${a.id}`) },
    )

  return (
    <div className="space-y-10 pt-6">
      <ErrorMessage error={create.error ?? archive.error} />
      <section aria-labelledby="mine-h" className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h2 id="mine-h" className="text-lg font-semibold tracking-tight">
            {t('helpers.mine')}
          </h2>
          <Button
            size="sm"
            disabled={create.isPending}
            onClick={() =>
              start(t('helpers.new_name'), '', localized(BLANK_SPEC, ['helpers.blank.input'], t))
            }
          >
            {create.isPending ? <Spinner /> : <Plus data-icon="inline-start" />}
            {t('helpers.new')}
          </Button>
        </div>
        {agents.isPending ? (
          <ListSkeleton />
        ) : agents.error ? (
          <ErrorMessage error={agents.error} />
        ) : agents.data.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed px-6 py-12 text-center">
            <Trio size={56} />
            <h3 className="pt-2 text-lg font-semibold">{t('helpers.empty')}</h3>
            <p className="max-w-sm text-sm text-muted-foreground">{t('helpers.empty_hint')}</p>
          </div>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agents.data.map((a) => (
              <ItemCard
                key={a.id}
                to={`/helpers/${a.id}`}
                title={a.name}
                lead={
                  <Tint palette={a.avatar.palette}>
                    <Avatar spec={a.avatar} size={56} />
                  </Tint>
                }
                version={a.current_version}
                updatedAt={a.updated_at}
                archiving={archive.isPending}
                onArchive={(reset) => archive.mutate(a.id, { onSettled: reset })}
              >
                <p className="line-clamp-2 text-sm text-muted-foreground">
                  {a.description || t('helpers.no_goal')}
                </p>
              </ItemCard>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="starters-h" className="space-y-4">
        <div>
          <h2 id="starters-h" className="text-lg font-semibold tracking-tight">
            {t('helpers.starters')}
          </h2>
          <p className="text-sm text-muted-foreground">{t('helpers.ui.templates_hint')}</p>
        </div>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {STARTERS.map((s) => {
            const av = avatarFromSeed(s.id)
            return (
              <li
                key={s.id}
                className={cn(
                  'flex flex-col gap-3 rounded-2xl border bg-muted/30 p-4 hover:bg-card',
                  LIFT,
                )}
              >
                <div className="flex items-center gap-3">
                  <Tint palette={av.palette}>
                    <Avatar spec={av} size={44} />
                  </Tint>
                  <div className="min-w-0">
                    <p className="font-semibold">{t(s.name)}</p>
                    <p className="text-sm text-muted-foreground">{t(s.goal)}</p>
                  </div>
                </div>
                <TemplateChips s={s} />
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-auto self-start"
                  disabled={create.isPending}
                  onClick={() => start(t(s.name), t(s.goal), localized(s.spec, s.inputLabels, t))}
                >
                  {t('helpers.use_starter')}
                  <ArrowRight data-icon="inline-end" />
                </Button>
              </li>
            )
          })}
        </ul>
      </section>
    </div>
  )
}
