import '@/features/helpers/lib'
import { MessageCircle, Pencil, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { cn } from 'cn'
import { useI18n, useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Modal } from '@/components/Modal'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Button, buttonVariants } from '@/components/ui/button'
import { toolText, useTools } from '@/features/tools/api'
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
      title={t('nav.agents')}
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

const COACH = avatarFromSeed('coach')
const COACH_TOOLS = ['profile_read', 'job_lookup', 'fit_read', 'web_search'] // backend DEFAULT_TOOLS

function ChatLink({ to, name }: { to: string; name: string }) {
  const t = useT()
  return (
    <Link
      to={to}
      aria-label={`${t('helpers.chat')}: ${name}`}
      className={buttonVariants({ variant: 'outline', size: 'sm' })}
    >
      <MessageCircle data-icon="inline-start" />
      {t('helpers.chat')}
    </Link>
  )
}

/** The tools an agent may use in chat, by name. */
function ToolChips({ ids }: { ids: string[] }) {
  const t = useT()
  if (!ids.length) return null
  return (
    <ul aria-label={t('nav.tools')} className="flex flex-wrap gap-1">
      {ids.map((id) => (
        <li key={id} className="rounded bg-muted px-1.5 text-xs leading-5">
          {toolText(t, id, 'name')}
        </li>
      ))}
    </ul>
  )
}

function PickModal({
  open,
  onClose,
  pending,
  onPick,
}: {
  open: boolean
  onClose: () => void
  pending: boolean
  onPick: (p: Pick) => void
}) {
  const t = useT()
  return (
    <Modal open={open} label={t('helpers.new')} onClose={onClose}>
      <h2 className="mb-4 text-lg font-semibold">{t('helpers.new')}</h2>
      <div className="grid gap-2 sm:grid-cols-2">
        {PICKS.map((p) => (
          <button
            key={p}
            type="button"
            disabled={pending}
            onClick={() => onPick(p)}
            className="rounded-xl border p-3 text-left outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
          >
            <span className="block font-medium">
              {p === 'custom' ? t('helpers.pick.custom_title') : t(`helpers.role.${p}`)}
            </span>
          </button>
        ))}
      </div>
      <Button variant="ghost" size="sm" className="mt-4" onClick={onClose}>
        {t('helpers.cancel')}
      </Button>
    </Modal>
  )
}

function AgentCard({
  a,
  archive,
}: {
  a: NonNullable<ReturnType<typeof useAgents>['data']>[number]
  archive: ReturnType<typeof useArchiveAgent>
}) {
  const t = useT()
  return (
    <ItemCard
      title={a.name}
      lead={
        <Tint palette={a.avatar.palette}>
          <Avatar spec={a.avatar} size={48} />
        </Tint>
      }
      footer={
        <>
          <ChatLink to={`/chat?agent=${a.id}`} name={a.name} />
          <Link
            to={`/helpers/${a.id}`}
            aria-label={`${t('helpers.edit')}: ${a.name}`}
            className={buttonVariants({ variant: 'ghost', size: 'sm' })}
          >
            <Pencil data-icon="inline-start" />
            {t('helpers.edit')}
          </Link>
          <span className="ml-auto rounded-full bg-muted px-2 py-0.5 font-medium tabular-nums">
            v{a.current_version}
          </span>
          <ConfirmButton
            variant="ghost"
            className="text-muted-foreground"
            label={t('helpers.archive')}
            confirmLabel={t('helpers.archive_confirm')}
            cancelLabel={t('helpers.cancel')}
            pending={archive.isPending}
            onConfirm={(reset) => archive.mutate(a.id, { onSettled: reset })}
          />
        </>
      }
    >
      {a.description && (
        <p className="line-clamp-2 text-sm text-muted-foreground">{a.description}</p>
      )}
      <ToolChips ids={a.tools} />
    </ItemCard>
  )
}

function Starters({
  pending,
  start,
}: {
  pending: boolean
  start: (name: string, description: string, spec: VersionSpec) => void
}) {
  const t = useT()
  return (
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
              <p className="min-w-0 flex-1 truncate text-sm font-medium">{t(s.name)}</p>
              <Button
                variant="outline"
                size="sm"
                aria-label={`${t('helpers.use_starter')}: ${t(s.name)}`}
                disabled={pending}
                onClick={() => start(t(s.name), '', localized(s.spec, s.inputLabels, t))}
              >
                {t('helpers.use_starter')}
              </Button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function HelpersTab({ picking, onClose }: { picking: boolean; onClose: () => void }) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const agents = useAgents()
  const create = useCreateAgent()
  const archive = useArchiveAgent()
  const tools = useTools()

  const start = (name: string, description: string, spec: VersionSpec) =>
    create.mutate(
      { name, description, spec, note: '' },
      { onSuccess: (a) => navigate(`/helpers/${a.id}`) },
    )

  const pick = (p: Pick) =>
    p === 'custom'
      ? start(t('helpers.new_name'), '', localized(BLANK_SPEC, ['helpers.fixed.notes'], t))
      : start(t(`helpers.role.${p}`), '', pickSpec(p))

  return (
    <div className="space-y-8">
      <ErrorMessage error={create.error ?? archive.error} />
      <PickModal open={picking} onClose={onClose} pending={create.isPending} onPick={pick} />
      <ul aria-label={t('nav.agents')} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <ItemCard
          title={t('nav.coach')}
          lead={
            <Tint palette={COACH.palette}>
              <Avatar spec={COACH} size={48} />
            </Tint>
          }
          footer={<ChatLink to="/chat" name={t('nav.coach')} />}
        >
          <ToolChips
            ids={(tools.data ?? []).filter((x) => COACH_TOOLS.includes(x.id)).map((x) => x.id)}
          />
        </ItemCard>
        {agents.data?.map((a) => (
          <AgentCard key={a.id} a={a} archive={archive} />
        ))}
      </ul>
      {agents.isPending ? (
        <ListSkeleton />
      ) : agents.error ? (
        <ErrorMessage error={agents.error} />
      ) : (
        agents.data.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('helpers.empty')}</p>
        )
      )}

      <Starters pending={create.isPending} start={start} />
    </div>
  )
}
