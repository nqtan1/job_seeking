import { Play, Sparkles } from 'lucide-react'
import { useRef, useState } from 'react'
import { useT } from '@/i18n'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Modal } from '@/components/Modal'
import { Spinner } from '@/components/Spinner'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useAiUse } from '@/features/radar/api'
import { type FlowDetail, useStartRun } from './api'
import { type Graph, MAX_INPUT_CHARS, type Specs, aiCalls, toolOf } from './graph'
import { JobSelect } from './ui'

/** Inputs, a job when a helper needs one, and the price before it starts: "up to N of your M". */
export function RunDialog({
  open,
  flow,
  graph,
  specs,
  onStarted,
  onClose,
}: {
  open: boolean
  flow: FlowDetail
  graph: Graph
  specs: Specs
  onStarted: (runId: string) => void
  onClose: () => void
}) {
  const t = useT()
  const start = useStartRun()
  const use = useAiUse()
  const [values, setValues] = useState<Record<string, string>>({})
  const [jobId, setJobId] = useState('')
  // The idempotency key belongs to one exact request: a double click or a retry after a lost
  // response reuses it (one run), while editing the inputs starts a new request (a new key).
  const attempt = useRef({ sig: '', key: '' })
  const keyFor = (sig: string) => {
    if (attempt.current.sig !== sig) attempt.current = { sig, key: crypto.randomUUID() }
    return attempt.current.key
  }

  const input = graph.nodes.find((n) => n.type === 'input')
  const fields = input?.type === 'input' ? input.fields : []
  const needsJob = graph.nodes.some(
    (n) =>
      (n.type === 'tool' && !!toolOf(n.tool)?.needs_job) ||
      (n.type === 'agent' &&
        (specs.get(n.agent_version_id)?.context_sources ?? []).some(
          (s) => s === 'job' || s === 'fit',
        )),
  )
  const need = aiCalls(graph)
  const left = use.data ? Math.max(use.data.quota - use.data.used, 0) : null
  const missing =
    fields.some((f) => (f.required ?? true) && !(values[f.name] ?? '').trim()) ||
    (needsJob && !jobId)
  const tooMany = left !== null && need > left

  return (
    <Modal open={open} label={t('helpers.run_flow')} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          start.mutate(
            {
              id: flow.id,
              inputs: values,
              jobId: jobId || null,
              key: keyFor(JSON.stringify([values, jobId])),
            },
            { onSuccess: (run) => onStarted(run.id) },
          )
        }}
      >
        <h2 className="text-lg font-semibold tracking-tight">{flow.name}</h2>
        {fields.map((f) => (
          <div key={f.name} className="space-y-1.5">
            <Label htmlFor={`run-${f.name}`}>{f.label}</Label>
            <Textarea
              id={`run-${f.name}`}
              rows={3}
              maxLength={MAX_INPUT_CHARS}
              value={values[f.name] ?? ''}
              onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
            />
          </div>
        ))}
        {needsJob && <JobSelect id="run-job" value={jobId} onChange={setJobId} />}
        <p
          className={`flex items-start gap-2 rounded-xl border px-3 py-2.5 text-sm ${tooMany ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'bg-muted/50 text-muted-foreground'}`}
        >
          <Sparkles aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>
            {left === null
              ? t('helpers.flow.cost', { count: need })
              : t('helpers.run.price', { need, left })}
          </span>
        </p>
        <ErrorMessage error={start.error} />
        <div className="flex justify-end gap-2 border-t pt-4">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('helpers.cancel')}
          </Button>
          <Button type="submit" disabled={missing || start.isPending || tooMany}>
            {start.isPending ? <Spinner /> : <Play data-icon="inline-start" />}
            {t('helpers.live.watch')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
