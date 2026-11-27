import { FlaskConical, Play, RefreshCw, TriangleAlert, X } from 'lucide-react'
import { useState } from 'react'
import { type Key, catalogs, useT } from '@/i18n'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Modal } from '@/components/Modal'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { Spinner } from '@/components/Spinner'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { type Tool, toolText, useTools } from '@/features/tools/api'
import { useToolsStatus, useTryTool } from './api'
import { OutputList } from './EdgeInspector'
import { MAX_INPUT_CHARS } from './graph'
import { toolFields } from './samples'
import { JobSelect, Result } from './ui'

type T = ReturnType<typeof useT>
type Status = ReturnType<typeof useToolsStatus>
// a link to the Start step in flows: nothing a person types
const HIDDEN = new Set(['start'])
const LONG = new Set(['body', 'text', 'notes'])
const known = (t: T, key: string) => (key in catalogs.en ? t(key as Key) : '')

/** Studio › Tools (ADR 0043): the tools agents can use, whether the tools service answers, and a
 *  side panel to run one for real with what it needs, showing exactly what it gives back. */
export function AgentToolsPage() {
  const t = useT()
  const tools = useTools()
  const status = useToolsStatus()
  const [open, setOpen] = useState<Tool | null>(null)
  const list = (tools.data ?? []).filter((x) => x.mcp)
  return (
    <Page
      title={t('nav.tools')}
      description={t('helpers.tools.intro')}
      actions={<ServiceStatus status={status} />}
    >
      {tools.isPending ? (
        <ListSkeleton />
      ) : tools.error ? (
        <ErrorMessage error={tools.error} />
      ) : list.length === 0 ? (
        <EmptyState icon={FlaskConical} title={t('helpers.tools.empty')} />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {list.map((tool) => (
            <ToolCard
              key={tool.id}
              tool={tool}
              served={status.data?.served}
              onTry={() => setOpen(tool)}
            />
          ))}
        </ul>
      )}
      <Modal
        side
        open={open !== null}
        label={open ? toolText(t, open.id, 'name') : ''}
        onClose={() => setOpen(null)}
      >
        {open && <TryPanel key={open.id} tool={open} onClose={() => setOpen(null)} />}
      </Modal>
    </Page>
  )
}

function ServiceStatus({ status }: { status: Status }) {
  const t = useT()
  const s = status.data
  return (
    <div className="flex items-center gap-2 text-sm" role="status">
      <span className="text-muted-foreground">{t('helpers.tools.service')}</span>
      {status.isFetching ? (
        <Spinner />
      ) : !s ? null : !s.remote ? (
        <StatusBadge>{t('helpers.tools.inprocess')}</StatusBadge>
      ) : s.ok ? (
        <StatusBadge tone="success">{t('helpers.tools.online', { ms: s.latency_ms })}</StatusBadge>
      ) : (
        <StatusBadge tone="danger">{t('helpers.tools.offline')}</StatusBadge>
      )}
      <Button
        size="icon-sm"
        variant="ghost"
        aria-label={t('helpers.tools.check')}
        title={t('helpers.tools.check')}
        disabled={status.isFetching}
        onClick={() => status.refetch()}
      >
        <RefreshCw />
      </Button>
    </div>
  )
}

function Facts({ tool }: { tool: Tool }) {
  const t = useT()
  return (
    <div className="flex flex-wrap gap-1.5">
      {tool.effect === 'read' ? (
        <StatusBadge>{t('helpers.tools.reads')}</StatusBadge>
      ) : (
        <StatusBadge tone="warning">{t('helpers.tools.writes')}</StatusBadge>
      )}
      {tool.ai_uses > 0 && (
        <StatusBadge tone="info">{t('helpers.tools.ai_uses', { count: tool.ai_uses })}</StatusBadge>
      )}
      {tool.needs_job && <StatusBadge>{t('helpers.tools.needs_job')}</StatusBadge>}
      {tool.daily_cap !== null && (
        <StatusBadge>{t('helpers.tools.cap', { count: tool.daily_cap })}</StatusBadge>
      )}
    </div>
  )
}

function ToolCard({
  tool,
  served,
  onTry,
}: {
  tool: Tool
  served: string[] | null | undefined
  onTry: () => void
}) {
  const t = useT()
  const name = toolText(t, tool.id, 'name')
  // only a running service can be missing a tool (an older image than the api)
  const missing = served != null && !served.includes(tool.id)
  return (
    <li className="flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-xs">
      <div className="flex items-start justify-between gap-2">
        <h2 className="leading-tight font-semibold">{name}</h2>
        {missing ? (
          <StatusBadge tone="danger">{t('helpers.tools.not_served')}</StatusBadge>
        ) : (
          served != null && <StatusBadge tone="success">{t('helpers.tools.ready')}</StatusBadge>
        )}
      </div>
      <p className="line-clamp-3 text-sm text-muted-foreground">{toolText(t, tool.id, 'about')}</p>
      <Facts tool={tool} />
      <div className="mt-auto">
        <Button
          size="sm"
          variant="outline"
          aria-label={t('helpers.tools.try_label', { name })}
          onClick={onTry}
        >
          <FlaskConical data-icon="inline-start" />
          {t('helpers.tools.try')}
        </Button>
      </div>
    </li>
  )
}

function InputField({
  tool,
  name,
  required,
  value,
  onChange,
}: {
  tool: string
  name: string
  required: boolean
  value: string
  onChange: (v: string) => void
}) {
  const t = useT()
  const id = `tool-in-${name}`
  const hint = known(t, `helpers.fixed.${name}.hint`)
  const example = known(t, `helpers.fixed.${name}.example`)
  const props = {
    id,
    value,
    maxLength: MAX_INPUT_CHARS,
    placeholder: example && t('helpers.tools.example', { text: example }),
    'aria-describedby': hint ? `${id}-hint` : undefined,
    onChange: (e: { target: { value: string } }) => onChange(e.target.value),
  }
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>
        {known(t, `helpers.fixed.${tool}.${name}`) || known(t, `helpers.fixed.${name}`) || name}
        {!required && (
          <span className="font-normal text-muted-foreground">
            {' '}
            ({t('helpers.tools.optional')})
          </span>
        )}
      </Label>
      {LONG.has(name) ? <Textarea rows={4} {...props} /> : <Input {...props} />}
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  )
}

function TryPanel({ tool, onClose }: { tool: Tool; onClose: () => void }) {
  const t = useT()
  const run = useTryTool()
  const [values, setValues] = useState<Record<string, string>>({})
  const [jobId, setJobId] = useState('')
  const inputs = tool.inputs.filter((i) => !HIDDEN.has(i.name))
  const missingText = inputs.some((i) => i.required && !(values[i.name] ?? '').trim())
  const why =
    tool.needs_job && !jobId
      ? t('helpers.ui.try_need_job')
      : missingText
        ? t('helpers.ui.try_need_text')
        : null
  const go = () =>
    run.mutate({
      id: tool.id,
      inputs: Object.fromEntries(
        inputs.filter((i) => (values[i.name] ?? '').trim()).map((i) => [i.name, values[i.name]]),
      ),
      jobId: jobId || null,
    })
  return (
    <div className="flex h-full flex-col">
      <header className="flex items-start gap-3 border-b px-5 py-4">
        <div className="min-w-0 flex-1 space-y-2">
          <h2 className="text-lg font-semibold tracking-tight">{toolText(t, tool.id, 'name')}</h2>
          <p className="text-sm text-muted-foreground">{toolText(t, tool.id, 'about')}</p>
          <Facts tool={tool} />
        </div>
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label={t('helpers.tools.close')}
          onClick={onClose}
        >
          <X />
        </Button>
      </header>
      <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
        <section aria-labelledby="tool-needs" className="space-y-3">
          <h3 id="tool-needs" className="text-sm font-semibold">
            {t('helpers.tools.needs')}
          </h3>
          {inputs.length === 0 && !tool.needs_job && (
            <p className="text-sm text-muted-foreground">{t('helpers.tools.no_inputs')}</p>
          )}
          {inputs.map((i) => (
            <InputField
              key={i.name}
              tool={tool.id}
              name={i.name}
              required={i.required}
              value={values[i.name] ?? ''}
              onChange={(v) => setValues((old) => ({ ...old, [i.name]: v }))}
            />
          ))}
          {tool.needs_job && <JobSelect id="tool-job" value={jobId} onChange={setJobId} />}
        </section>
        {tool.effect !== 'read' && (
          <p className="flex items-start gap-2 rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning">
            <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
            {t('helpers.tools.writes_warn')}
          </p>
        )}
        <div className="space-y-2">
          <Button disabled={!!why || run.isPending} onClick={go}>
            {run.isPending ? <Spinner /> : <Play data-icon="inline-start" />}
            {run.isPending ? t('helpers.running') : t('helpers.run')}
          </Button>
          {why && <p className="text-xs text-muted-foreground">{why}</p>}
        </div>
        <ErrorMessage error={run.error} />
        <section aria-labelledby="tool-gives" aria-live="polite" className="space-y-3">
          <h3 id="tool-gives" className="text-sm font-semibold">
            {run.data ? t('helpers.tools.result') : t('helpers.tools.gives')}
          </h3>
          {run.data ? (
            <div className="overflow-hidden rounded-xl border bg-background">
              <div className="p-4">
                <Result value={run.data.outputs} large />
              </div>
              <p className="border-t bg-muted/40 px-4 py-2 text-xs text-muted-foreground tabular-nums">
                {t(run.data.remote ? 'helpers.tools.on_service' : 'helpers.tools.in_app', {
                  ms: run.data.latency_ms,
                })}
              </p>
            </div>
          ) : (
            <OutputList fields={toolFields(tool.outputs)} bare />
          )}
        </section>
      </div>
    </div>
  )
}
