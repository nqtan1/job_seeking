import '@/features/helpers/lib'
import {
  ArrowRight,
  Briefcase,
  Coins,
  FileText,
  Plus,
  Rows3,
  Sparkles,
  UserRound,
  Workflow,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { cn } from 'cn'
import { type Key, useI18n, useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Modal } from '@/components/Modal'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Spinner } from '@/components/Spinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  useAgents,
  useArchiveAgent,
  useArchiveFlow,
  useCreateAgent,
  useCreateFlow,
  useFlows,
  type AgentDetail,
} from './api'
import { Avatar } from './Avatar'
import { RunsTab } from './RunsPage'
import { ItemCard } from './ui'
import { LIFT } from './lib'
import { PALETTES, avatarFromSeed } from './avatar'
import { type VersionSpec, MAX_HELPERS, emptyGraph } from './graph'
import {
  BLANK_SPEC,
  STARTERS,
  type Starter,
  TEMPLATES,
  type Template,
  localized,
  templateGraph,
} from './starters'

const TABS = ['helpers', 'flows', 'runs'] as const

export function HelpersPage() {
  const t = useT()
  const [params] = useSearchParams()
  const p = params.get('tab')
  const tab = p === 'flows' || p === 'runs' ? p : 'helpers'
  return (
    <Page title={t('helpers.title')} description={t('helpers.subtitle')}>
      <Hero />
      <nav
        aria-label={t('helpers.title')}
        className="inline-flex gap-1 rounded-xl bg-muted p-1 text-sm"
      >
        {TABS.map((k) => (
          <Link
            key={k}
            to={k === 'helpers' ? '/helpers' : `/helpers?tab=${k}`}
            replace
            aria-current={tab === k ? 'page' : undefined}
            className="rounded-lg px-4 py-1.5 font-medium text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 aria-[current=page]:bg-background aria-[current=page]:text-foreground aria-[current=page]:shadow-sm pointer-coarse:py-2.5"
          >
            {k === 'runs' ? t('helpers.pages.runs') : t(`helpers.tab.${k}`)}
          </Link>
        ))}
      </nav>
      <div>{tab === 'helpers' ? <HelpersTab /> : tab === 'flows' ? <FlowsTab /> : <RunsTab />}</div>
    </Page>
  )
}

/** A few characters that overlap, so an empty page still feels inhabited. */
function Trio({ size }: { size: number }) {
  return (
    <div className="flex items-end -space-x-3" aria-hidden>
      {['followup', 'pitch', 'reply'].map((id, i) => (
        <span key={id} className={cn(i === 1 && '-translate-y-2')}>
          <Avatar spec={avatarFromSeed(id)} size={size} />
        </span>
      ))}
    </div>
  )
}

function Hero() {
  const t = useT()
  return (
    <div className="relative flex items-center justify-between gap-6 overflow-hidden rounded-2xl border bg-gradient-to-br from-primary/10 via-accent/40 to-transparent px-6 py-6 sm:px-8">
      <div className="max-w-xl space-y-1.5">
        <h2 className="text-xl font-semibold tracking-tight text-balance sm:text-2xl">
          {t('helpers.ui.hero_title')}
        </h2>
        <p className="text-sm text-muted-foreground sm:text-base">{t('helpers.ui.hero_body')}</p>
      </div>
      <div className="hidden shrink-0 sm:block">
        <Trio size={64} />
      </div>
    </div>
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

function FlowsTab() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const flows = useFlows()
  const create = useCreateFlow()
  const archive = useArchiveFlow()
  const [naming, setNaming] = useState(false)
  const [name, setName] = useState('')

  const make = () =>
    create.mutate(
      {
        name: name.trim(),
        description: '',
        graph: emptyGraph('notes', 'result', [
          t('helpers.flow.input_label'),
          t('helpers.flow.output_label'),
        ]),
        note: '',
      },
      { onSuccess: (f) => navigate(`/helpers/flows/${f.id}`) },
    )

  return (
    <div className="space-y-4 pt-6">
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={() => setNaming(true)}>
          <Plus data-icon="inline-start" />
          {t('helpers.flow.new')}
        </Button>
      </div>
      <ReadyMade />
      <ErrorMessage error={archive.error} />
      {flows.isPending ? (
        <ListSkeleton />
      ) : flows.error ? (
        <ErrorMessage error={flows.error} />
      ) : flows.data.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed px-6 py-12 text-center">
          <div className="flex items-center gap-2 text-muted-foreground" aria-hidden>
            <Avatar spec={avatarFromSeed('followup')} size={44} />
            <ArrowRight className="size-4" />
            <Avatar spec={avatarFromSeed('redflags')} size={44} />
            <ArrowRight className="size-4" />
            <Rows3 className="size-6" />
          </div>
          <h3 className="pt-2 text-lg font-semibold">{t('helpers.flow.empty')}</h3>
          <p className="max-w-sm text-sm text-muted-foreground">{t('helpers.flow.empty_hint')}</p>
        </div>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {flows.data.map((f) => (
            <ItemCard
              key={f.id}
              to={`/helpers/flows/${f.id}`}
              title={f.name}
              lead={
                <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-accent text-accent-foreground">
                  <Workflow className="size-5" aria-hidden />
                </span>
              }
              version={f.current_version}
              updatedAt={f.updated_at}
              archiving={archive.isPending}
              onArchive={(reset) => archive.mutate(f.id, { onSettled: reset })}
            >
              <p className="mt-1 inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                <Coins className="size-3" aria-hidden />
                {t('helpers.ui.flow_cost', { count: f.max_ai_calls })}
              </p>
            </ItemCard>
          ))}
        </ul>
      )}

      <Modal open={naming} label={t('helpers.flow.new')} onClose={() => setNaming(false)}>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (name.trim()) make()
          }}
          className="space-y-4"
        >
          <h2 className="font-semibold">{t('helpers.flow.new')}</h2>
          <div className="space-y-1.5">
            <Label htmlFor="flow-name">{t('helpers.name')}</Label>
            <Input
              id="flow-name"
              autoFocus
              maxLength={80}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <ErrorMessage error={create.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setNaming(false)}>
              {t('helpers.cancel')}
            </Button>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              {create.isPending && <Spinner />}
              {t('helpers.flow.create')}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}

/** Three automations that set up their helpers and the flow in one click. A retry after a failure
 *  reuses the helpers already created, so nothing is made twice. */
function ReadyMade() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const agents = useAgents()
  const createAgent = useCreateAgent()
  const createFlow = useCreateFlow()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<{
    id: string
    cause?: unknown
    cap?: number
    partial?: boolean
  } | null>(null)
  const made = useRef(new Map<string, AgentDetail[]>())

  const build = async (tpl: Template) => {
    const have = made.current.get(tpl.id) ?? []
    const need = tpl.helpers.length - have.length
    if (agents.data && agents.data.length + need > MAX_HELPERS) {
      setError({ id: tpl.id, cap: need })
      return
    }
    setBusy(tpl.id)
    setError(null)
    try {
      for (const sid of tpl.helpers.slice(have.length)) {
        const s = STARTERS.find((x) => x.id === sid)!
        have.push(
          await createAgent.mutateAsync({
            name: t(s.name),
            description: t(s.goal),
            spec: localized(s.spec, s.inputLabels, t),
            note: '',
          }),
        )
        made.current.set(tpl.id, have)
      }
      const flow = await createFlow.mutateAsync({
        name: t(tpl.name),
        description: '',
        graph: templateGraph(
          tpl,
          have.map((a) => ({ agent_id: a.id, agent_version_id: a.version_id })),
          t,
        ),
        note: '',
      })
      made.current.delete(tpl.id)
      navigate(`/helpers/flows/${flow.id}`)
    } catch (cause) {
      setError({ id: tpl.id, cause, partial: made.current.has(tpl.id) })
    } finally {
      setBusy(null)
    }
  }

  return (
    <section aria-labelledby="ready-h" className="space-y-3">
      <div>
        <h2 id="ready-h" className="text-lg font-semibold tracking-tight">
          {t('helpers.pages.tpl.title')}
        </h2>
        <p className="text-sm text-muted-foreground">{t('helpers.pages.tpl.hint')}</p>
      </div>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {TEMPLATES.map((tpl) => (
          <li
            key={tpl.id}
            className={cn('flex flex-col gap-3 rounded-2xl border bg-muted/30 p-4', LIFT)}
          >
            <div className="flex items-center gap-3">
              <span className="flex -space-x-2" aria-hidden>
                {tpl.helpers.map((h) => (
                  <Avatar key={h} spec={avatarFromSeed(h)} size={40} />
                ))}
              </span>
              <div className="min-w-0">
                <p className="font-semibold">{t(tpl.name)}</p>
                <p className="text-sm text-muted-foreground">{t(tpl.hint)}</p>
              </div>
            </div>
            <Button
              variant="outline"
              className="mt-auto self-start"
              disabled={busy !== null}
              onClick={() => build(tpl)}
            >
              {busy === tpl.id ? <Spinner /> : <Sparkles data-icon="inline-start" />}
              {busy === tpl.id ? t('helpers.pages.tpl.busy') : t('helpers.pages.tpl.use')}
            </Button>
            {error?.id === tpl.id &&
              (error.cap ? (
                <p
                  role="alert"
                  className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
                >
                  {t('helpers.pages.tpl.cap', { max: MAX_HELPERS, count: error.cap })}
                </p>
              ) : (
                <div className="space-y-2">
                  {error.partial && (
                    <p className="text-sm text-muted-foreground">
                      {t('helpers.pages.tpl.partial')}
                    </p>
                  )}
                  <ErrorMessage error={error.cause} />
                </div>
              ))}
          </li>
        ))}
      </ul>
    </section>
  )
}
