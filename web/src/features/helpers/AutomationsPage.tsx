import '@/features/helpers/lib'
import { ArrowRight, Coins, Plus, Rows3, Sparkles, Workflow } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { cn } from 'cn'
import { useI18n, useT } from '@/i18n'
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
  useArchiveFlow,
  useCreateAgent,
  useCreateFlow,
  useFlows,
  type AgentDetail,
} from './api'
import { Avatar } from './Avatar'
import { RunsTab } from './RunsPage'
import { ContactsTab } from './Recipients'
import { Hero, ItemCard } from './ui'
import { LIFT } from './lib'
import { avatarFromSeed } from './avatar'
import { MAX_HELPERS, emptyGraph } from './graph'
import { STARTERS, TEMPLATES, type Template, localized, templateGraph } from './starters'

const TABS = ['flows', 'runs', 'contacts'] as const

const LABEL = {
  flows: 'helpers.tab.flows',
  runs: 'helpers.pages.runs',
  contacts: 'helpers.tab.contacts',
} as const

export function AutomationsPage() {
  const t = useT()
  const [params] = useSearchParams()
  const q = params.get('tab')
  const tab = q === 'runs' || q === 'contacts' ? q : 'flows'
  return (
    <Page title={t('helpers.auto.title')} description={t('helpers.auto.subtitle')}>
      <Hero title={t('helpers.auto.hero_title')} body={t('helpers.auto.hero_body')} />
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
      <div>{tab === 'flows' ? <FlowsTab /> : tab === 'runs' ? <RunsTab /> : <ContactsTab />}</div>
    </Page>
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
      { onSuccess: (f) => navigate(`/automations/${f.id}`) },
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
              to={`/automations/${f.id}`}
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
      navigate(`/automations/${flow.id}`)
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
