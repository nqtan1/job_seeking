import { Play } from 'lucide-react'
import { useState } from 'react'
import { useT } from '@/i18n'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Spinner } from '@/components/Spinner'
import { useAiUse } from '@/features/radar/api'
import { MAX_INPUT_CHARS, type VersionSpec } from './graph'
import { JobSelect, Result } from './ui'
import { useTrial } from './api'

/** "Try it": runs the draft (unsaved) once on sample text or a real job. Nothing is stored. */
export function TryPanel({
  agentId,
  spec,
  receives = true,
}: {
  agentId: string
  spec: VersionSpec
  /** Show "What the AI receives" under the answer (the editor puts it in Advanced instead). */
  receives?: boolean
}) {
  const t = useT()
  const trial = useTrial()
  const use = useAiUse()
  const [values, setValues] = useState<Record<string, string>>({})
  const [jobId, setJobId] = useState('')
  const inputs = spec.inputs ?? []
  const sources = spec.context_sources ?? []
  const needsJob = sources.includes('job') || sources.includes('fit')
  const missing =
    inputs.some((i) => (i.required ?? true) && !(values[i.name] ?? '').trim()) ||
    (needsJob && !jobId)
  const left = use.data ? Math.max(use.data.quota - use.data.used, 0) : null
  // a disabled button must say why: the first thing still missing
  const why =
    needsJob && !jobId
      ? t('helpers.ui.try_need_job')
      : missing
        ? t('helpers.ui.try_need_text')
        : null

  return (
    <section aria-labelledby="try-h" className="space-y-4 rounded-xl border bg-card p-5 shadow-xs">
      <h2 id="try-h" className="font-semibold tracking-tight">
        {t('helpers.try')}
      </h2>
      {inputs.map((i) => (
        <div key={i.name} className="space-y-1.5">
          <Label htmlFor={`try-${i.name}`}>{i.label}</Label>
          <Textarea
            id={`try-${i.name}`}
            rows={3}
            maxLength={MAX_INPUT_CHARS}
            value={values[i.name] ?? ''}
            onChange={(e) => setValues({ ...values, [i.name]: e.target.value })}
          />
        </div>
      ))}
      {needsJob && <JobSelect id="try-job" value={jobId} onChange={setJobId} />}
      {sources.includes('fit') && (
        <p className="text-xs text-muted-foreground">{t('helpers.ui.try_fit_hint')}</p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          disabled={missing || trial.isPending || left === 0}
          onClick={() =>
            trial.mutate({
              id: agentId,
              spec,
              // only what the draft declares: a renamed or removed input must not travel along
              inputs: Object.fromEntries(inputs.map((i) => [i.name, values[i.name] ?? ''])),
              jobId: jobId || null,
            })
          }
        >
          {trial.isPending ? <Spinner /> : <Play data-icon="inline-start" />}
          {trial.isPending ? t('helpers.running') : t('helpers.run')}
        </Button>
        {left !== null && (
          <span className="text-xs text-muted-foreground">
            {left === 0 ? t('helpers.no_uses_left') : t('helpers.uses_left', { count: left })}
          </span>
        )}
      </div>
      {why && left !== 0 && <p className="text-xs text-muted-foreground">{why}</p>}
      <ErrorMessage error={trial.error} />
      <div aria-live="polite">
        {trial.data && (
          <div className="overflow-hidden rounded-xl border bg-background">
            <div className="p-4">
              <Result value={trial.data.result} large />
            </div>
            <p className="border-t bg-muted/40 px-4 py-2 text-xs text-muted-foreground tabular-nums">
              {trial.data.model} · {(trial.data.latency_ms / 1000).toFixed(1)} s
            </p>
          </div>
        )}
      </div>
      {receives && <Receives spec={spec} />}
    </section>
  )
}

/** "What the AI receives": the exact list of what one run sends, for the curious. */
export function Receives({ spec }: { spec: VersionSpec }) {
  const t = useT()
  const inputs = spec.inputs ?? []
  const sources = spec.context_sources ?? []
  return (
    <details className="rounded-lg bg-muted/40 px-3 py-2 text-sm">
      <summary className="cursor-pointer text-muted-foreground">{t('helpers.receives')}</summary>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs text-muted-foreground">
        <li>{t('helpers.receives.frame')}</li>
        <li>{t('helpers.receives.instructions')}</li>
        {inputs.map((i) => (
          <li key={i.name}>{t('helpers.receives.data', { name: i.name })}</li>
        ))}
        {sources.map((s) => (
          <li key={s}>{t('helpers.receives.data', { name: s })}</li>
        ))}
      </ol>
      <p className="mt-2 text-xs text-muted-foreground">{t('helpers.receives.never')}</p>
    </details>
  )
}
