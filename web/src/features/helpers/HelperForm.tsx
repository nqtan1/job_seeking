import {
  Brain,
  Briefcase,
  Compass,
  FileText,
  Plus,
  Rows3,
  Sparkles,
  Target,
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
import { MAX_FIELDS, MAX_INPUTS, type VersionSpec, freeName } from './graph'
import { toolText, useTools } from '@/features/tools/api'
import { ChoiceCard } from './ui'

export { Receives, TryPanel } from './TryPanel'

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

const SOURCE_ICON = {
  profile: UserRound,
  job: Briefcase,
  fit: Target,
  memory: Brain,
  situation: Compass,
} as const

/** A flat titled group inside "Advanced": no card, at most one short hint. */
function Block({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium">{title}</h3>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {children}
    </section>
  )
}

/** The main thing to write: the instructions (or, for a built-in type, only extra preferences). */
export function InstructionsField({
  spec,
  onChange,
}: {
  spec: VersionSpec
  onChange: (next: VersionSpec) => void
}) {
  const t = useT()
  const built = (spec.role ?? 'custom') !== 'custom'
  const max = built ? 1000 : 4000
  return (
    <div className="space-y-1.5">
      <Label htmlFor="h-instructions">
        {built ? t('helpers.role.prefs_title') : t('helpers.instructions')}
      </Label>
      <Textarea
        id="h-instructions"
        rows={built ? 4 : 9}
        maxLength={max}
        className="leading-relaxed"
        value={spec.instructions}
        onChange={(e) => onChange({ ...spec, instructions: e.target.value })}
      />
      <p className="text-right text-xs text-muted-foreground tabular-nums">
        {spec.instructions.length} / {max}
      </p>
    </div>
  )
}

type SetSpec = (patch: Partial<VersionSpec>) => void
type Part = { spec: VersionSpec; set: SetSpec }

function RoleBlock({ spec, set }: Part) {
  const t = useT()
  const role = spec.role ?? 'custom'
  const built = role !== 'custom'
  return (
    <Block title={t('helpers.role.title')}>
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
      {built && <p className="text-sm text-muted-foreground">{t(`helpers.role.${role}.about`)}</p>}
    </Block>
  )
}

function InputsBlock({ spec, set }: Part) {
  const t = useT()
  const inputs = spec.inputs ?? []
  const setInput = (i: number, patch: Partial<NonNullable<VersionSpec['inputs']>[number]>) =>
    set({ inputs: inputs.map((x, k) => (k === i ? { ...x, ...patch } : x)) })
  return (
    <Block title={t('helpers.inputs')}>
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
    </Block>
  )
}

function SourcesBlock({ spec, set }: Part) {
  const t = useT()
  const sources = spec.context_sources ?? []
  return (
    <Block title={t('helpers.sources')} hint={t('helpers.sources_help')}>
      <div className="grid gap-2 sm:grid-cols-3">
        {(['profile', 'job', 'fit', 'memory', 'situation'] as const).map((s) => (
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
    </Block>
  )
}

function FieldRow({ fields, f, i, set }: { fields: Field[]; f: Field; i: number; set: SetSpec }) {
  const t = useT()
  const setField = (i: number, patch: Partial<Field>) =>
    set({
      output: { kind: 'fields', fields: fields.map((f, k) => (k === i ? { ...f, ...patch } : f)) },
    })
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-muted/40 p-2">
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
  )
}

function ResultBlock({ spec, set }: Part) {
  const t = useT()
  const fields = spec.output.fields ?? []
  return (
    <Block title={t('helpers.result')}>
      <fieldset tabIndex={-1} className="space-y-3 outline-none">
        <div className="grid gap-2 sm:grid-cols-2">
          {(['text', 'fields'] as const).map((k) => (
            <ChoiceCard
              key={k}
              type="radio"
              name="result-kind"
              icon={k === 'text' ? FileText : Rows3}
              title={t(`helpers.result.${k}`)}
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
          fields.map((f, i) => <FieldRow key={i} fields={fields} f={f} i={i} set={set} />)}
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
    </Block>
  )
}

function QualityBlock({ spec, set }: Part) {
  const t = useT()
  return (
    <Block title={t('helpers.quality')}>
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
            checked={(spec.model_tier ?? 'fast') === q}
            onChange={() => set({ model_tier: q })}
          />
        ))}
      </div>
    </Block>
  )
}

/** The technical part of a helper, for "Advanced": type, inputs, sources, result shape, quality. */
export function SpecForm({
  spec,
  onChange,
}: {
  spec: VersionSpec
  onChange: (next: VersionSpec) => void
}) {
  const set = (patch: Partial<VersionSpec>) => onChange({ ...spec, ...patch })
  const built = (spec.role ?? 'custom') !== 'custom' // a built-in role: tested prompt and format, only preferences are ours

  return (
    <div className="space-y-5">
      <RoleBlock spec={spec} set={set} />

      {!built && (
        <>
          <InputsBlock spec={spec} set={set} />
          <SourcesBlock spec={spec} set={set} />
          <ResultBlock spec={spec} set={set} />
        </>
      )}

      <ToolPicker value={spec.tools ?? []} onChange={(tools) => set({ tools })} />

      <QualityBlock spec={spec} set={set} />
    </div>
  )
}

const MAX_TOOLS = 12 // backend helpers/schemas.MAX_TOOLS

/** The tools the helper may use when you chat with it: the chat tools of the packs that are on. */
function ToolPicker({ value, onChange }: { value: string[]; onChange: (ids: string[]) => void }) {
  const t = useT()
  const tools = (useTools().data ?? []).filter((x) => x.chat)
  if (!tools.length) return null
  const full = value.length >= MAX_TOOLS
  return (
    <Block title={t('nav.tools')} hint={t('helpers.tools_max', { max: MAX_TOOLS })}>
      <div className="grid gap-2 sm:grid-cols-2">
        {tools.map(({ id }) => (
          <ChoiceCard
            key={id}
            type="checkbox"
            title={toolText(t, id, 'name')}
            checked={value.includes(id)}
            onChange={(on) =>
              on ? !full && onChange([...value, id]) : onChange(value.filter((x) => x !== id))
            }
          />
        ))}
      </div>
    </Block>
  )
}
