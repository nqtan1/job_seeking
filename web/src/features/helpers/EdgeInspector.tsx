import { ArrowRight, Info } from 'lucide-react'
import { useEffect, useState } from 'react'
import { type Key, catalogs, useT } from '@/i18n'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { Avatar } from './Avatar'
import { type Handoff, usePreview } from './api'
import type { AvatarSpec } from './avatar'
import {
  type Graph,
  type MapEntry,
  type Specs,
  EXTRA_INPUT,
  inputsOf,
  outputsOf,
  setMap,
} from './graph'
import { type OutField, outputFields } from './samples'

const CUSTOM = '__custom__'
const NONE = ''
const asField = (v: string) => /^\{\{\s*([a-z][a-z0-9_]*)\s*\}\}$/.exec(v)?.[1]

/** What moves from step A to step B: A's outputs, B's inputs, the mapping between them, a live
 *  preview rendered by the server (the very function the engine uses) and what B cannot see. */
export function EdgeInspector({
  graph,
  specs,
  edgeId,
  titles,
  avatars,
  readOnly,
  actual,
  onGraph,
}: {
  graph: Graph
  specs: Specs
  edgeId: string
  titles: ReadonlyMap<string, string>
  avatars: ReadonlyMap<string, AvatarSpec>
  readOnly?: boolean
  /** What really moved in a finished run (run page). */
  actual?: Handoff
  onGraph?: (g: Graph) => void
}) {
  const t = useT()
  const edge = graph.edges.find((e) => e.id === edgeId)
  const from = graph.nodes.find((n) => n.id === edge?.from.node)
  const to = graph.nodes.find((n) => n.id === edge?.to)
  const outs = from ? outputsOf(from, specs) : []
  const fields = from ? outputFields(from, specs) : []
  const example = (name: string) => fields.find((f) => f.name === name)?.example ?? ''
  const ins = to ? inputsOf(to, specs) : []
  const { sample, setSample, rendered } = useHandoffPreview(
    edge?.map,
    outs,
    example,
    readOnly,
    actual,
  )

  if (!edge || !from || !to) return null
  const update = (name: string, value: string | null) => {
    const rest = edge.map.filter((m) => m.input !== name)
    const map: MapEntry[] = value === null ? rest : [...rest, { input: name, value }]
    onGraph?.(setMap(graph, edge.id, map))
  }

  return (
    <section aria-label={t('helpers.handoff')} className="space-y-4 rounded-xl border bg-card p-4">
      <header className="space-y-1.5">
        <h2 className="flex flex-wrap items-center gap-x-2 gap-y-1 leading-tight font-semibold">
          {avatars.get(from.id) && <Avatar spec={avatars.get(from.id)!} size={24} />}
          {titles.get(from.id)}
          <ArrowRight aria-hidden className="size-4 text-muted-foreground" />
          {avatars.get(to.id) && <Avatar spec={avatars.get(to.id)!} size={24} />}
          {titles.get(to.id)}
        </h2>
        <OutputList fields={fields} />
      </header>

      <ul className="space-y-4">
        {ins.map((i) => (
          <MapRow
            key={i.name}
            i={i}
            m={edge.map.find((m) => m.input === i.name)}
            outs={outs}
            example={example}
            readOnly={readOnly}
            actual={actual}
            rendered={rendered}
            update={update}
          />
        ))}
      </ul>

      {!actual && outs.length > 0 && (
        <SampleInputs outs={outs} example={example} sample={sample} setSample={setSample} />
      )}
      {(actual?.truncated || rendered?.truncated) && (
        <p
          role="status"
          className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs"
        >
          {t('helpers.handoff.truncated')}
        </p>
      )}
      <CannotSee />
    </section>
  )
}

/** Sample outputs typed by the person, rendered by the server after a pause. */
function useHandoffPreview(
  map: MapEntry[] | undefined,
  outs: string[],
  example: (name: string) => string,
  readOnly: boolean | undefined,
  actual: Handoff | undefined,
) {
  const t = useT()
  const [sample, setSample] = useState<Record<string, string>>({})
  const { mutate: render, data: rendered } = usePreview()
  // What to ask the server to render (as a string, so the effect re-runs only when it changes);
  // null when there is nothing to preview: read-only, a real hand-off is shown, or no mapping yet.
  const request =
    readOnly || actual || !map || map.length === 0
      ? null
      : JSON.stringify({
          map,
          outputs: Object.fromEntries(
            outs.map((o) => [
              o,
              sample[o] ?? (example(o) || t('helpers.sample_value', { field: o })),
            ]),
          ),
        })

  useEffect(() => {
    if (!request) return
    const id = setTimeout(() => render(JSON.parse(request)), 400)
    return () => clearTimeout(id)
  }, [request, render])
  return { sample, setSample, rendered }
}

type Rendered = ReturnType<typeof usePreview>['data']

/** One input of step B: where it comes from and what it will receive. */
function MapRow({
  i,
  m,
  outs,
  example,
  readOnly,
  actual,
  rendered,
  update,
}: {
  i: ReturnType<typeof inputsOf>[number]
  m: MapEntry | undefined
  outs: string[]
  example: (name: string) => string
  readOnly?: boolean
  actual?: Handoff
  rendered: Rendered
  update: (name: string, value: string | null) => void
}) {
  const t = useT()
  const field = m ? asField(m.value) : undefined
  const mode = !m ? NONE : field && outs.includes(field) ? field : CUSTOM
  return (
    <li className="space-y-1.5">
      <label htmlFor={`map-${i.name}`} className="text-sm font-medium">
        {i.name === EXTRA_INPUT ? t('helpers.handoff.info') : i.name}
        {i.required && <span className="text-destructive"> *</span>}
      </label>
      <NativeSelect
        id={`map-${i.name}`}
        className="w-full"
        disabled={readOnly}
        value={mode}
        onChange={(e) => {
          const v = e.target.value
          if (v === NONE) update(i.name, null)
          else if (v === CUSTOM) update(i.name, m?.value ?? '')
          else update(i.name, `{{${v}}}`)
        }}
      >
        <option value={NONE}>{t('helpers.connections.not_connected')}</option>
        {outs.map((o) => (
          <option key={o} value={o}>
            {t('helpers.handoff.pass', { field: o })} — {example(o).slice(0, 32)}
          </option>
        ))}
        <option value={CUSTOM}>{t('helpers.handoff.custom')}</option>
      </NativeSelect>
      {mode === CUSTOM && (
        <Input
          aria-label={t('helpers.handoff.template')}
          disabled={readOnly}
          maxLength={2000}
          value={m?.value ?? ''}
          onChange={(e) => update(i.name, e.target.value)}
          className="font-mono text-xs"
        />
      )}
      {m && (
        <p className="rounded-r-lg border-l-2 border-primary/50 bg-muted/60 px-3 py-2 text-xs whitespace-pre-wrap">
          {actual ? String(actual.payload[i.name] ?? '') : (rendered?.values[i.name]?.text ?? '…')}
          <span className="ml-2 text-muted-foreground tabular-nums">
            {actual
              ? `${String(actual.payload[i.name] ?? '').length} ${t('helpers.chars')}`
              : rendered?.values[i.name]
                ? `${rendered.values[i.name].chars} ${t('helpers.chars')}`
                : ''}
          </span>
        </p>
      )}
    </li>
  )
}

function SampleInputs({
  outs,
  example,
  sample,
  setSample,
}: {
  outs: string[]
  example: (name: string) => string
  sample: Record<string, string>
  setSample: (s: Record<string, string>) => void
}) {
  const t = useT()
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-muted-foreground">
        {t('helpers.handoff.sample')}
      </summary>
      <div className="mt-2 space-y-2">
        {outs.map((o) => (
          <Input
            key={o}
            aria-label={o}
            placeholder={example(o) || o}
            value={sample[o] ?? ''}
            onChange={(e) => setSample({ ...sample, [o]: e.target.value })}
          />
        ))}
      </div>
    </details>
  )
}

function CannotSee() {
  const t = useT()
  return (
    <div className="flex gap-2.5 rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
      <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" />
      <div>
        <p className="font-medium text-foreground">{t('helpers.handoff.cannot_see')}</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          <li>{t('helpers.handoff.cannot.instructions')}</li>
          <li>{t('helpers.handoff.cannot.others')}</li>
          <li>{t('helpers.handoff.cannot.contact')}</li>
        </ul>
      </div>
    </div>
  )
}

/** What a step gives back: each field with what it means and an example, so a link can be wired by
 *  looking at it. */
export function OutputList({ fields }: { fields: OutField[] }) {
  const t = useT()
  if (!fields.length) return null
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium">{t('helpers.gives_back')}</p>
      <ul className="space-y-1.5">
        {fields.map((f) => {
          const key = `helpers.field.${f.name}`
          return (
            <li key={f.name} className="text-xs">
              <p>
                <span className="font-mono">{`{{${f.name}}}`}</span>
                {key in catalogs.en && (
                  <span className="text-muted-foreground"> · {t(key as Key)}</span>
                )}
              </p>
              <p className="mt-0.5 line-clamp-3 rounded-r-lg border-l-2 border-primary/40 bg-muted/60 px-2.5 py-1.5 whitespace-pre-wrap text-muted-foreground">
                {f.example}
              </p>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
