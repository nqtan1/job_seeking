import {
  Briefcase,
  FileText,
  FlaskConical,
  Gauge,
  ListChecks,
  PenLine,
  Play,
  Plus,
  Rows3,
  Shuffle,
  Sparkles,
  Target,
  TextCursorInput,
  UserRound,
  X,
  Zap,
} from 'lucide-react'
import { useState } from 'react'
import { useT } from '@/i18n'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/ui/native-select'
import { Textarea } from '@/components/ui/textarea'
import { MAX_FIELDS, MAX_INPUTS, MAX_INPUT_CHARS, type VersionSpec, freeName } from './graph'
import { ChoiceCard, JobSelect, Result, SectionCard } from './ui'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Spinner } from '@/components/Spinner'
import { useAiUse } from '@/features/radar/api'
import { useTrial } from './api'
import { Avatar } from './Avatar'
import {
  ACCESSORIES,
  type AvatarSpec,
  BODIES,
  EYES,
  PALETTES,
  PALETTES_COUNT,
  shuffled,
} from './avatar'

const NAME = /[^a-z0-9_]/g
const toName = (s: string) =>
  s
    .toLowerCase()
    .replace(/\s+/g, '_')
    .replace(NAME, '')
    .replace(/^[^a-z]+/, '')
    .slice(0, 32)

type Field = NonNullable<VersionSpec['output']['fields']>[number]

/** Comma-separated options: typed text is kept as typed, parsed into the list as you go. */
function OptionsInput({
  label,
  options,
  onChange,
}: {
  label: string
  options: string[]
  onChange: (next: string[]) => void
}) {
  const [text, setText] = useState(options.join(', '))
  return (
    <Input
      aria-label={label}
      className="min-w-40 flex-1"
      value={text}
      onChange={(e) => {
        setText(e.target.value)
        onChange(
          e.target.value
            .split(',')
            .map((o) => o.trim())
            .filter(Boolean)
            .slice(0, 8),
        )
      }}
    />
  )
}
const TYPES = ['text', 'number', 'boolean', 'choice', 'list'] as const

const ROLES = ['custom', 'letter', 'interview', 'cv_advice'] as const

const SOURCE_ICON = { profile: UserRound, job: Briefcase, fit: Target } as const

/** The editable part of a helper: instructions, inputs, sources, result shape, quality. Each is a
 *  card of its own so the form reads as a short list of decisions, not one long page. */
export function SpecForm({
  spec,
  onChange,
}: {
  spec: VersionSpec
  onChange: (next: VersionSpec) => void
}) {
  const t = useT()
  const set = (patch: Partial<VersionSpec>) => onChange({ ...spec, ...patch })
  const inputs = spec.inputs ?? []
  const fields = spec.output.fields ?? []
  const sources = spec.context_sources ?? []
  const role = spec.role ?? 'custom'
  const built = role !== 'custom' // a built-in role: tested prompt and format, only preferences are ours
  const setField = (i: number, patch: Partial<Field>) =>
    set({
      output: { kind: 'fields', fields: fields.map((f, k) => (k === i ? { ...f, ...patch } : f)) },
    })
  const setInput = (i: number, patch: Partial<NonNullable<VersionSpec['inputs']>[number]>) =>
    set({ inputs: inputs.map((x, k) => (k === i ? { ...x, ...patch } : x)) })

  return (
    <>
      <SectionCard icon={Sparkles} title={t('helpers.role.title')} help={t('helpers.role.help')}>
        <NativeSelect
          aria-label={t('helpers.role.title')}
          value={role}
          onChange={(e) => {
            const next = ROLES.find((r) => r === e.target.value) ?? 'custom'
            set(
              next === 'custom'
                ? { role: next }
                : { role: next, inputs: [], context_sources: ['profile', 'job', 'fit'] },
            )
          }}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`helpers.role.${r}`)}
            </option>
          ))}
        </NativeSelect>
        {built && (
          <p className="text-sm text-muted-foreground">{t(`helpers.role.${role}.about`)}</p>
        )}
      </SectionCard>

      <SectionCard
        icon={PenLine}
        title={built ? t('helpers.role.prefs_title') : t('helpers.ui.sec.instructions')}
        help={built ? t('helpers.role.prefs_help') : t('helpers.ui.sec.instructions_help')}
      >
        <div className="space-y-1.5">
          <Label htmlFor="h-instructions" className="sr-only">
            {t('helpers.instructions')}
          </Label>
          <Textarea
            id="h-instructions"
            rows={built ? 4 : 9}
            maxLength={built ? 1000 : 4000}
            className="leading-relaxed"
            value={spec.instructions}
            onChange={(e) => set({ instructions: e.target.value })}
            aria-describedby="h-instructions-help"
          />
          <p
            id="h-instructions-help"
            className="flex justify-between gap-3 text-xs text-muted-foreground"
          >
            <span>{built ? '' : t('helpers.instructions_help')}</span>
            <span className="shrink-0 tabular-nums">
              {spec.instructions.length} / {built ? 1000 : 4000}
            </span>
          </p>
        </div>
      </SectionCard>

      {!built && (
        <>
          <SectionCard
            icon={TextCursorInput}
            title={t('helpers.inputs')}
            help={t('helpers.inputs_help')}
          >
            <fieldset tabIndex={-1} className="space-y-2 outline-none">
              {inputs.map((inp, i) => (
                <div
                  key={i}
                  className="flex flex-wrap items-center gap-2 rounded-xl border bg-muted/40 p-2"
                >
                  <Input
                    aria-label={`${t('helpers.input_label')} ${i + 1}`}
                    className="min-w-40 flex-1 bg-background"
                    value={inp.label}
                    maxLength={60}
                    onChange={(e) =>
                      setInput(i, {
                        label: e.target.value,
                        name: inp.name || toName(e.target.value) || 'notes',
                      })
                    }
                  />
                  <Input
                    aria-label={`${t('helpers.input_name')} ${i + 1}`}
                    className="w-32 bg-background font-mono text-xs"
                    value={inp.name}
                    maxLength={32}
                    onChange={(e) => setInput(i, { name: toName(e.target.value) })}
                  />
                  <label className="flex items-center gap-1.5 px-1 text-sm">
                    <input
                      type="checkbox"
                      checked={inp.required ?? true}
                      onChange={(e) => setInput(i, { required: e.target.checked })}
                    />
                    {t('helpers.required')}
                  </label>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`${t('helpers.remove')}: ${inp.label || inp.name}`}
                    onClick={(e) => {
                      e.currentTarget.closest('fieldset')?.focus()
                      set({ inputs: inputs.filter((_, k) => k !== i) })
                    }}
                  >
                    <X />
                  </Button>
                </div>
              ))}
              {inputs.length < MAX_INPUTS && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    set({
                      inputs: [
                        ...inputs,
                        {
                          name: freeName(
                            'input',
                            inputs.map((x) => x.name),
                          ),
                          label: t('helpers.new_input'),
                          required: true,
                        },
                      ],
                    })
                  }
                >
                  <Plus data-icon="inline-start" />
                  {t('helpers.add_input')}
                </Button>
              )}
            </fieldset>
          </SectionCard>

          <SectionCard
            icon={FileText}
            title={t('helpers.sources')}
            help={t('helpers.sources_help')}
          >
            <div className="grid gap-2 sm:grid-cols-3">
              {(['profile', 'job', 'fit'] as const).map((s) => (
                <ChoiceCard
                  key={s}
                  type="checkbox"
                  icon={SOURCE_ICON[s]}
                  title={t(`helpers.source.${s}`)}
                  checked={sources.includes(s)}
                  onChange={(on) =>
                    set({
                      context_sources: on ? [...sources, s] : sources.filter((x) => x !== s),
                    })
                  }
                />
              ))}
            </div>
          </SectionCard>

          <SectionCard
            icon={ListChecks}
            title={t('helpers.result')}
            help={t('helpers.ui.sec.result_help')}
          >
            <fieldset tabIndex={-1} className="space-y-3 outline-none">
              <div className="grid gap-2 sm:grid-cols-2">
                {(['text', 'fields'] as const).map((k) => (
                  <ChoiceCard
                    key={k}
                    type="radio"
                    name="result-kind"
                    icon={k === 'text' ? FileText : Rows3}
                    title={t(`helpers.result.${k}`)}
                    hint={t(`helpers.ui.${k}_hint`)}
                    checked={spec.output.kind === k}
                    onChange={() =>
                      set({
                        output:
                          k === 'text'
                            ? { kind: 'text', fields: [] }
                            : {
                                kind: 'fields',
                                fields: fields.length
                                  ? fields
                                  : [{ name: 'answer', type: 'text', options: [] }],
                              },
                      })
                    }
                  />
                ))}
              </div>
              {spec.output.kind === 'fields' &&
                fields.map((f, i) => (
                  <div
                    key={i}
                    className="flex flex-wrap items-center gap-2 rounded-xl border bg-muted/40 p-2"
                  >
                    <Input
                      aria-label={`${t('helpers.field_name')} ${i + 1}`}
                      className="w-36 bg-background font-mono text-xs"
                      value={f.name}
                      maxLength={32}
                      onChange={(e) => setField(i, { name: toName(e.target.value) })}
                    />
                    <NativeSelect
                      aria-label={t('helpers.field_type')}
                      size="sm"
                      value={f.type}
                      onChange={(e) =>
                        setField(i, {
                          type: e.target.value as Field['type'],
                          options: e.target.value === 'choice' ? ['yes', 'no'] : [],
                        })
                      }
                    >
                      {TYPES.map((x) => (
                        <option key={x} value={x}>
                          {t(`helpers.type.${x}`)}
                        </option>
                      ))}
                    </NativeSelect>
                    {f.type === 'choice' && (
                      <OptionsInput
                        key={`${i}-${f.type}`}
                        label={t('helpers.field_options')}
                        options={f.options ?? []}
                        onChange={(options) => setField(i, { options })}
                      />
                    )}
                    {fields.length > 1 && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`${t('helpers.remove')}: ${f.name}`}
                        onClick={(e) => {
                          e.currentTarget.closest('fieldset')?.focus()
                          set({
                            output: { kind: 'fields', fields: fields.filter((_, k) => k !== i) },
                          })
                        }}
                      >
                        <X />
                      </Button>
                    )}
                  </div>
                ))}
              {spec.output.kind === 'fields' && fields.length < MAX_FIELDS && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    set({
                      output: {
                        kind: 'fields',
                        fields: [
                          ...fields,
                          {
                            name: freeName(
                              'field',
                              fields.map((x) => x.name),
                            ),
                            type: 'text',
                            options: [],
                          },
                        ],
                      },
                    })
                  }
                >
                  <Plus data-icon="inline-start" />
                  {t('helpers.add_field')}
                </Button>
              )}
            </fieldset>
          </SectionCard>
        </>
      )}

      <SectionCard icon={Gauge} title={t('helpers.quality')} help={t('helpers.quality_help')}>
        <div
          role="radiogroup"
          aria-label={t('helpers.quality')}
          className="grid gap-2 sm:grid-cols-2"
        >
          {(['fast', 'smart'] as const).map((q) => (
            <ChoiceCard
              key={q}
              type="radio"
              name="model-tier"
              icon={q === 'fast' ? Zap : Sparkles}
              title={t(`helpers.quality.${q}`)}
              hint={t(`helpers.ui.q.${q}_hint`)}
              checked={(spec.model_tier ?? 'fast') === q}
              onChange={() => set({ model_tier: q })}
            />
          ))}
        </div>
      </SectionCard>
    </>
  )
}

/** "Try it": runs the draft (unsaved) once on sample text or a real job. Nothing is stored. */
export function TryPanel({ agentId, spec }: { agentId: string; spec: VersionSpec }) {
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

  return (
    <section aria-labelledby="try-h" className="space-y-4 rounded-xl border bg-card p-5 shadow-xs">
      <header className="flex items-start gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
          <FlaskConical className="size-4" aria-hidden />
        </span>
        <div>
          <h2 id="try-h" className="leading-8 font-semibold tracking-tight">
            {t('helpers.try')}
          </h2>
          <p className="-mt-1 text-sm text-muted-foreground">{t('helpers.ui.try_hint')}</p>
        </div>
      </header>
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
      <ErrorMessage error={trial.error} />
      <div aria-live="polite">
        {trial.data ? (
          <div className="overflow-hidden rounded-xl border bg-background">
            <div className="p-4">
              <Result value={trial.data.result} large />
            </div>
            <p className="border-t bg-muted/40 px-4 py-2 text-xs text-muted-foreground tabular-nums">
              {trial.data.model} · {(trial.data.latency_ms / 1000).toFixed(1)} s
            </p>
          </div>
        ) : (
          !trial.isPending &&
          !trial.error && (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
              <Sparkles className="size-5 text-primary/70" aria-hidden />
              {t('helpers.ui.try_empty')}
            </div>
          )
        )}
      </div>
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
    </section>
  )
}

const range = (n: number) => Array.from({ length: n }, (_, i) => i)

function Row({
  label,
  field,
  count,
  value,
  onChange,
}: {
  label: string
  field: 'body' | 'eyes' | 'accessory'
  count: number
  value: AvatarSpec
  onChange: (next: AvatarSpec) => void
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1.5">
      <span className="w-14 shrink-0 text-xs font-medium text-muted-foreground">{label}</span>
      {range(count).map((i) => (
        <button
          key={i}
          type="button"
          aria-pressed={value[field] === i}
          aria-label={`${label} ${i + 1}`}
          onClick={() => onChange({ ...value, [field]: i })}
          className="grid size-8 place-items-center rounded-lg border bg-background outline-none transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 aria-pressed:border-primary aria-pressed:bg-accent pointer-coarse:size-11"
        >
          <Avatar spec={{ ...value, [field]: i }} size={24} />
        </button>
      ))}
    </div>
  )
}

/** Pick a character: shuffle for a surprise, or choose each part. Parameters only (no uploads). */
export function AvatarPicker({
  value,
  onChange,
}: {
  value: AvatarSpec
  onChange: (next: AvatarSpec) => void
}) {
  const t = useT()
  return (
    <div className="flex flex-wrap items-start gap-5 rounded-xl bg-muted/40 p-4">
      <div className="flex flex-col items-center gap-2">
        <Avatar spec={value} size={104} label={t('helpers.avatar')} />
        <Button variant="outline" size="sm" onClick={() => onChange(shuffled())}>
          <Shuffle data-icon="inline-start" />
          {t('helpers.shuffle')}
        </Button>
      </div>
      <div className="min-w-0 flex-1 space-y-2.5">
        <Row
          value={value}
          onChange={onChange}
          label={t('helpers.avatar.body')}
          field="body"
          count={BODIES}
        />
        <Row
          value={value}
          onChange={onChange}
          label={t('helpers.avatar.eyes')}
          field="eyes"
          count={EYES}
        />
        <Row
          value={value}
          onChange={onChange}
          label={t('helpers.avatar.extra')}
          field="accessory"
          count={ACCESSORIES}
        />
        <div
          role="group"
          aria-label={t('helpers.avatar.color')}
          className="flex flex-wrap items-center gap-1"
        >
          <span className="w-14 shrink-0 text-xs font-medium text-muted-foreground">
            {t('helpers.avatar.color')}
          </span>
          {range(PALETTES_COUNT).map((i) => (
            <button
              key={i}
              type="button"
              aria-pressed={value.palette === i}
              aria-label={`${t('helpers.avatar.color')} ${i + 1}`}
              onClick={() => onChange({ ...value, palette: i })}
              style={{ background: PALETTES[i].fill, borderColor: PALETTES[i].accent }}
              className="size-5 rounded-full border-2 outline-none focus-visible:ring-3 focus-visible:ring-ring/50 aria-pressed:ring-2 aria-pressed:ring-foreground pointer-coarse:size-9"
            />
          ))}
        </div>
      </div>
    </div>
  )
}
