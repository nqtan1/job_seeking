import '@/features/helpers/lib'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { cn } from 'cn'
import { useI18n, useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Modal } from '@/components/Modal'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { useAgents, useArchiveAgent, useCreateAgent } from './api'
import { Avatar } from './Avatar'
import { ItemCard } from './ui'
import { LIFT } from './lib'
import { PALETTES, avatarFromSeed } from './avatar'
import type { VersionSpec } from './graph'
import { BLANK_SPEC, PICKS, STARTERS, type Pick, localized, pickSpec } from './starters'

export function HelpersPage() {
  const t = useT()
  const [picking, setPicking] = useState(false)
  return (
    <Page
      title={t('helpers.title')}
      actions={
        <Button size="sm" onClick={() => setPicking(true)}>
          <Plus data-icon="inline-start" />
          {t('helpers.new')}
        </Button>
      }
    >
      <HelpersTab picking={picking} onClose={() => setPicking(false)} />
    </Page>
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

function HelpersTab({ picking, onClose }: { picking: boolean; onClose: () => void }) {
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

  const pick = (p: Pick) =>
    p === 'custom'
      ? start(t('helpers.new_name'), '', localized(BLANK_SPEC, ['helpers.blank.input'], t))
      : start(t(`helpers.role.${p}`), '', pickSpec(p))

  return (
    <div className="space-y-8">
      <ErrorMessage error={create.error ?? archive.error} />
      <Modal open={picking} label={t('helpers.new')} onClose={onClose}>
        <h2 className="mb-4 text-lg font-semibold">{t('helpers.new')}</h2>
        <div className="grid gap-2 sm:grid-cols-2">
          {PICKS.map((p) => (
            <button
              key={p}
              type="button"
              disabled={create.isPending}
              onClick={() => pick(p)}
              className="rounded-xl border p-3 text-left outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
            >
              <span className="block font-medium">
                {p === 'custom' ? t('helpers.pick.custom_title') : t(`helpers.role.${p}`)}
              </span>
              <span className="block text-xs text-muted-foreground">
                {t(`helpers.pick.about.${p}`)}
              </span>
            </button>
          ))}
        </div>
        <Button variant="ghost" size="sm" className="mt-4" onClick={onClose}>
          {t('helpers.cancel')}
        </Button>
      </Modal>
      {agents.isPending ? (
        <ListSkeleton />
      ) : agents.error ? (
        <ErrorMessage error={agents.error} />
      ) : agents.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('helpers.empty')}</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {agents.data.map((a) => (
            <ItemCard
              key={a.id}
              to={`/helpers/${a.id}`}
              title={a.name}
              lead={
                <Tint palette={a.avatar.palette}>
                  <Avatar spec={a.avatar} size={48} />
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

      <section aria-labelledby="starters-h" className="space-y-3">
        <h2 id="starters-h" className="text-sm font-medium text-muted-foreground">
          {t('helpers.starters')}
        </h2>
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {STARTERS.map((s) => {
            const av = avatarFromSeed(s.id)
            return (
              <li
                key={s.id}
                className={cn('flex items-center gap-3 rounded-2xl border bg-card p-3', LIFT)}
              >
                <Tint palette={av.palette}>
                  <Avatar spec={av} size={36} />
                </Tint>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{t(s.name)}</p>
                  <p className="truncate text-xs text-muted-foreground">{t(s.goal)}</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  aria-label={`${t('helpers.use_starter')}: ${t(s.name)}`}
                  disabled={create.isPending}
                  onClick={() => start(t(s.name), t(s.goal), localized(s.spec, s.inputLabels, t))}
                >
                  {t('helpers.use_starter')}
                </Button>
              </li>
            )
          })}
        </ul>
      </section>
    </div>
  )
}
