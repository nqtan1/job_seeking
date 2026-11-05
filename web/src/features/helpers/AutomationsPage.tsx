import '@/features/helpers/lib'
import { Ellipsis, Plus, Sparkles, Target } from 'lucide-react'
import { type ReactNode, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { cn } from 'cn'
import { useI18n, useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Modal } from '@/components/Modal'
import { Page } from '@/components/Page'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ListSkeleton } from '@/components/Skeleton'
import { Spinner } from '@/components/Spinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  useAgents,
  useAllRuns,
  useArchiveFlow,
  useCreateAgent,
  useCreateFlow,
  useFlows,
  type AgentDetail,
  useInstallJobHunter,
} from './api'
import { Avatar } from './Avatar'
import { RunsTab } from './RunsPage'
import { ConnectionsTab } from './Connections'
import { ContactsTab } from './Recipients'
import { RunStatusBadge } from './ui'
import { LIFT, relTime } from './lib'
import { avatarFromSeed } from './avatar'
import { MAX_HELPERS, emptyGraph } from './graph'
import { STARTERS, TEMPLATES, type Template, localized, templateGraph } from './starters'

const TABS = ['flows', 'runs', 'accounts'] as const

const LABEL = {
  flows: 'helpers.tab.flows',
  runs: 'helpers.tab.history',
  accounts: 'helpers.tab.accounts',
} as const

// Older links: ?tab=contacts and ?tab=connections both land on Accounts.
const ALIAS: Record<string, (typeof TABS)[number]> = {
  contacts: 'accounts',
  connections: 'accounts',
}

export function AutomationsPage() {
  const t = useT()
  const [params] = useSearchParams()
  const q = params.get('tab') ?? ''
  const tab = TABS.find((k) => k === q) ?? ALIAS[q] ?? 'flows'
  const [naming, setNaming] = useState(false)
  return (
    <Page
      title={t('helpers.auto.title')}
      actions={
        tab === 'flows' && (
          <Button onClick={() => setNaming(true)}>
            <Plus data-icon="inline-start" />
            {t('helpers.flow.new')}
          </Button>
        )
      }
    >
      <nav
        aria-label={t('helpers.auto.sections')}
        className="inline-flex gap-1 rounded-xl bg-muted p-1 text-sm"
      >
        {TABS.map((k) => (
          <Link
            key={k}
            to={k === 'flows' ? '/automations' : `/automations?tab=${k}`}
            replace
            aria-current={tab === k ? 'page' : undefined}
            className="rounded-lg px-4 py-1.5 font-medium text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 aria-[current=page]:bg-background aria-[current=page]:text-foreground aria-[current=page]:shadow-sm pointer-coarse:py-2.5"
          >
            {t(LABEL[k])}
          </Link>
        ))}
      </nav>
      {tab === 'flows' ? (
        <FlowsTab naming={naming} setNaming={setNaming} />
      ) : tab === 'runs' ? (
        <RunsTab />
      ) : (
        <div className="space-y-10">
          <ConnectionsTab />
          <ContactsTab />
        </div>
      )}
    </Page>
  )
}

function FlowsTab({ naming, setNaming }: { naming: boolean; setNaming: (v: boolean) => void }) {
  const { t, locale } = useI18n()
  const navigate = useNavigate()
  const flows = useFlows()
  const runs = useAllRuns({})
  const create = useCreateFlow()
  const archive = useArchiveFlow()
  const [name, setName] = useState('')
  // Runs come newest first, so the first one seen for a flow is its last run.
  const last = new Map<string, NonNullable<typeof runs.data>['pages'][number][number]>()
  for (const r of runs.data?.pages.flat() ?? []) if (!last.has(r.flow_id)) last.set(r.flow_id, r)

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
      { onSuccess: (f) => navigate(`/automations/${f.id}`) },
    )

  return (
    <div className="space-y-8">
      <ReadyMade />
      <ErrorMessage error={archive.error} />
      {flows.isPending ? (
        <ListSkeleton />
      ) : flows.error ? (
        <ErrorMessage error={flows.error} />
      ) : flows.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('helpers.flow.empty')}</p>
      ) : (
        <ul className="divide-y rounded-2xl border">
          {flows.data.map((f) => {
            const run = last.get(f.id)
            return (
              <li key={f.id} className="flex items-center gap-3 p-3 pl-4">
                <Link
                  to={`/automations/${f.id}`}
                  className="min-w-0 flex-1 truncate rounded font-medium outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  {f.name}
                </Link>
                {run && (
                  <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                    <RunStatusBadge status={run.status} />
                    <span className="hidden sm:inline">{relTime(run.created_at, locale)}</span>
                  </span>
                )}
                <details className="relative shrink-0">
                  <summary
                    aria-label={t('helpers.flow.more', { name: f.name })}
                    className="grid size-8 cursor-pointer list-none place-items-center rounded-lg text-muted-foreground outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 [&::-webkit-details-marker]:hidden"
                  >
                    <Ellipsis className="size-4" aria-hidden />
                  </summary>
                  <div className="absolute right-0 z-10 mt-1 flex gap-1 rounded-xl border bg-popover p-2 shadow-md">
                    <ConfirmButton
                      variant="ghost"
                      label={t('helpers.archive')}
                      confirmLabel={t('helpers.archive_confirm')}
                      cancelLabel={t('helpers.cancel')}
                      pending={archive.isPending}
                      onConfirm={(reset) => archive.mutate(f.id, { onSettled: reset })}
                    />
                  </div>
                </details>
              </li>
            )
          })}
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
          <Label htmlFor="flow-name" className="sr-only">
            {t('helpers.name')}
          </Label>
          <Input
            id="flow-name"
            autoFocus
            maxLength={80}
            placeholder={t('helpers.name')}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
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

/** The ready-made job hunter: type a search as a sentence and it prepares each new offer. */
function JobHunterTile() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const install = useInstallJobHunter()
  return (
    <Tile
      icon={
        <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-primary/10 text-primary">
          <Target className="size-5" aria-hidden />
        </span>
      }
      name={t('helpers.hunter.title')}
      hint={t('helpers.hunter.body')}
      busy={install.isPending}
      busyLabel={t('helpers.pages.tpl.busy')}
      disabled={install.isPending}
      onUse={() =>
        install.mutate(undefined, { onSuccess: (f) => navigate(`/automations/${f.id}`) })
      }
    >
      <ErrorMessage error={install.error} />
    </Tile>
  )
}

/** One compact tile: name, a few words, one button. */
function Tile({
  icon,
  name,
  hint,
  busy,
  busyLabel,
  disabled,
  onUse,
  children,
}: {
  icon: ReactNode
  name: string
  hint: string
  busy: boolean
  busyLabel: string
  disabled: boolean
  onUse: () => void
  children?: ReactNode
}) {
  const { t } = useI18n()
  return (
    <li className={cn('flex flex-col gap-3 rounded-2xl border bg-card p-4', LIFT)}>
      <div className="flex items-center gap-3">
        {icon}
        <div className="min-w-0">
          <p className="font-semibold">{name}</p>
          <p className="text-sm text-muted-foreground">{hint}</p>
        </div>
      </div>
      <Button
        variant="outline"
        className="mt-auto self-start"
        disabled={disabled}
        aria-label={t('helpers.pages.tpl.use_label', { name })}
        onClick={onUse}
      >
        {busy ? <Spinner /> : <Sparkles data-icon="inline-start" />}
        {busy ? busyLabel : t('helpers.pages.tpl.use')}
      </Button>
      {children}
    </li>
  )
}

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
      navigate(`/automations/${flow.id}`)
    } catch (cause) {
      setError({ id: tpl.id, cause, partial: made.current.has(tpl.id) })
    } finally {
      setBusy(null)
    }
  }

  return (
    <section aria-labelledby="ready-h" className="space-y-3">
      <h2 id="ready-h" className="text-lg font-semibold tracking-tight">
        {t('helpers.pages.tpl.title')}
      </h2>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <JobHunterTile />
        {TEMPLATES.map((tpl) => (
          <Tile
            key={tpl.id}
            icon={
              <span className="flex -space-x-2" aria-hidden>
                {tpl.helpers.map((h) => (
                  <Avatar key={h} spec={avatarFromSeed(h)} size={36} />
                ))}
              </span>
            }
            name={t(tpl.name)}
            hint={t(tpl.hint)}
            busy={busy === tpl.id}
            busyLabel={t('helpers.pages.tpl.busy')}
            disabled={busy !== null}
            onUse={() => build(tpl)}
          >
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
          </Tile>
        ))}
      </ul>
    </section>
  )
}
