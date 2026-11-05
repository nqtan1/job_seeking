import {
  ArrowRight,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  FlaskConical,
  Info,
  Plus,
  TriangleAlert,
  X,
} from 'lucide-react'
import { type Key, catalogs, useT } from '@/i18n'
import { Avatar } from './Avatar'
import { type Handoff, useAgent, useFlows, usePreview } from './api'
import { type AvatarSpec, PALETTES } from './avatar'
import {
  type Graph,
  type GraphNode,
  type Issue,
  MAX_INPUT_CHARS,
  type MapEntry,
  type Specs,
  type VersionSpec,
  freeName,
  EXTRA_INPUT,
  inputsOf,
  outputsOf,
  patchNode,
  setMap,
  typeKey,
  MAX_FIXED_CHARS,
  mappedInputs,
  typeableInputs,
} from './graph'
import type { Selection } from './Canvas'
import { KIND } from './nodeKind'
import { type OutField, outputFields } from './samples'
import { useEffect, useState } from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/ui/native-select'
import { Link, useParams } from 'react-router'
import { TryPanel } from './HelperForm'
import { Button } from '@/components/ui/button'

/** One status line: "Ready", or only what is wrong. Every row jumps to the step. */
export function ValidationPanel({
  titles,
  issues,
  onJump,
}: {
  titles: ReadonlyMap<string, string>
  issues: Issue[] | undefined
  onJump: (s: Selection) => void
}) {
  const t = useT()
  const errors = (issues ?? []).filter((i) => i.severity === 'error')
  const warnings = (issues ?? []).filter((i) => i.severity === 'warning')
  const rows = [...errors, ...warnings]
  return (
    <section aria-label={t('helpers.checks')} className="space-y-1">
      <p
        role="status"
        className={`flex items-center gap-2 px-1 text-sm ${errors.length ? 'font-medium text-destructive' : 'text-muted-foreground'}`}
      >
        {errors.length ? (
          <CircleAlert aria-hidden className="size-4 shrink-0" />
        ) : (
          <CircleCheck aria-hidden className="size-4 shrink-0 text-success" />
        )}
        {errors.length
          ? t('helpers.checks.problems', { count: errors.length })
          : t('helpers.checks.ok')}
      </p>
      {rows.length > 0 && (
        <ul className="space-y-0.5">
          {rows.map((i, k) => (
            <li key={k}>
              <button
                type="button"
                onClick={() =>
                  onJump(
                    i.edge_id
                      ? { kind: 'edge', id: i.edge_id }
                      : i.node_id
                        ? { kind: 'node', id: i.node_id }
                        : null,
                  )
                }
                className="flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 pointer-coarse:min-h-11"
              >
                {i.severity === 'error' ? (
                  <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
                ) : (
                  <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" />
                )}
                <span>
                  <span className="sr-only">{t(`helpers.sev.${i.severity}`)}: </span>
                  {i.node_id && titles.get(i.node_id) && (
                    <strong className="font-medium">{titles.get(i.node_id)}: </strong>
                  )}
                  {
                    t(
                      `helpers.issue.${i.code}` as 'helpers.issue.cycle',
                    ) /* server codes are a closed set */
                  }
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Who({
  id,
  graph,
  titles,
  avatars,
}: {
  id: string
  graph: Graph
  titles: ReadonlyMap<string, string>
  avatars: ReadonlyMap<string, AvatarSpec>
}) {
  const type = graph.nodes.find((n) => n.id === id)?.type
  const Icon = type ? KIND[type].icon : null
  return (
    <span className={`kind ${type ? KIND[type].cls : ''} flex items-center gap-2`}>
      {avatars.get(id) ? (
        <Avatar spec={avatars.get(id)!} size={22} />
      ) : (
        Icon && <Icon aria-hidden className="size-3.5" style={{ color: 'var(--k)' }} />
      )}
      <span className="truncate">{titles.get(id)}</span>
    </span>
  )
}

/** The text alternative to the canvas, and the audit of every hand-off. */
export function DataFlowTable({
  graph,
  titles,
  avatars,
  handoffs,
  onSelect,
}: {
  graph: Graph
  titles: ReadonlyMap<string, string>
  avatars: ReadonlyMap<string, AvatarSpec>
  handoffs?: Handoff[]
  onSelect: (s: Selection) => void
}) {
  const t = useT()
  if (graph.edges.length === 0) return null
  const actual = new Map((handoffs ?? []).map((h) => [h.edge_id, h]))
  return (
    <section
      aria-label={t('helpers.dataflow')}
      className="overflow-x-auto rounded-xl border bg-card"
    >
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{t('helpers.dataflow')}</caption>
        <thead className="border-b text-xs font-medium text-muted-foreground">
          <tr>
            <th scope="col" className="px-4 py-2.5">
              {t('helpers.dataflow.from')}
            </th>
            <th scope="col" className="px-4 py-2.5">
              {t('helpers.dataflow.to')}
            </th>
            <th scope="col" className="px-4 py-2.5">
              {t('helpers.dataflow.fields')}
            </th>
            {handoffs && (
              <th scope="col" className="px-4 py-2.5">
                {t('helpers.dataflow.size')}
              </th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {graph.edges.map((e) => {
            const a = actual.get(e.id)
            const size = a
              ? Object.values(a.payload).reduce<number>((n, v) => n + String(v).length, 0)
              : null
            return (
              <tr key={e.id}>
                <td className="px-4 py-2.5">
                  <Who id={e.from.node} graph={graph} titles={titles} avatars={avatars} />
                </td>
                <td className="px-4 py-2.5">
                  <button
                    type="button"
                    className="rounded outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                    aria-label={`${titles.get(e.from.node)} → ${titles.get(e.to)}`}
                    onClick={() => onSelect({ kind: 'edge', id: e.id })}
                  >
                    <Who id={e.to} graph={graph} titles={titles} avatars={avatars} />
                  </button>
                </td>
                <td className="px-4 py-2.5 font-mono text-xs">
                  {e.map.map((m) => m.input).join(', ') || '—'}
                </td>
                {handoffs && (
                  <td className="px-4 py-2.5 tabular-nums">
                    {size === null
                      ? '—'
                      : `${size} ${t('helpers.chars')}${a?.truncated ? ' ⚠' : ''}`}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}

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
  const [sample, setSample] = useState<Record<string, string>>({})
  const { mutate: render, data: rendered } = usePreview()
  const map = edge?.map
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

  if (!edge || !from || !to) return null
  const entry = (name: string) => edge.map.find((m) => m.input === name)
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
        {ins.map((i) => {
          const m = entry(i.name)
          const field = m ? asField(m.value) : undefined
          const mode = !m ? NONE : field && outs.includes(field) ? field : CUSTOM
          return (
            <li key={i.name} className="space-y-1.5">
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
                <option value={NONE}>{t('helpers.handoff.none')}</option>
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
                  {actual
                    ? String(actual.payload[i.name] ?? '')
                    : (rendered?.values[i.name]?.text ?? '…')}
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
        })}
      </ul>

      {!actual && outs.length > 0 && (
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
      )}
      {(actual?.truncated || rendered?.truncated) && (
        <p
          role="status"
          className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs"
        >
          {t('helpers.handoff.truncated')}
        </p>
      )}
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
    </section>
  )
}

type FieldList = { name: string; label: string; required?: boolean }[]
const toName = (s: string) =>
  s
    .toLowerCase()
    .replace(/\s+/g, '_')
    .replace(/[^a-z0-9_]/g, '')
    .replace(/^[^a-z]+/, '')
    .slice(0, 32)

function Fields({
  value,
  onChange,
  max = 6,
}: {
  value: FieldList
  onChange: (v: FieldList) => void
  max?: number
}) {
  const t = useT()
  return (
    <div tabIndex={-1} className="space-y-2 outline-none">
      {value.map((f, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input
            aria-label={`${t('helpers.input_label')} ${i + 1}`}
            value={f.label}
            maxLength={60}
            onChange={(e) =>
              onChange(value.map((x, k) => (k === i ? { ...x, label: e.target.value } : x)))
            }
          />
          <Input
            aria-label={`${t('helpers.input_name')} ${i + 1}`}
            className="w-28 font-mono text-xs"
            value={f.name}
            maxLength={32}
            onChange={(e) =>
              onChange(value.map((x, k) => (k === i ? { ...x, name: toName(e.target.value) } : x)))
            }
          />
          {value.length > 1 && (
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={`${t('helpers.remove')}: ${f.label || f.name}`}
              onClick={(e) => {
                e.currentTarget.parentElement?.parentElement?.focus()
                onChange(value.filter((_, k) => k !== i))
              }}
            >
              <X />
            </Button>
          )}
        </div>
      ))}
      {value.length < max && (
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            onChange([
              ...value,
              {
                name: freeName(
                  'field',
                  value.map((x) => x.name),
                ),
                label: t('helpers.new_input'),
                required: true,
              },
            ])
          }
        >
          <Plus data-icon="inline-start" />
          {t('helpers.add_input')}
        </Button>
      )}
    </div>
  )
}

const MAX_WAIT_MINUTES = 7 * 24 * 60

/** 150 -> "2 h 30 min" */
const hoursMinutes = (m: number) => {
  const d = Math.floor(m / 1440)
  const h = Math.floor((m % 1440) / 60)
  const r = m % 60
  return [d && `${d} d`, h && `${h} h`, (r || m === 0) && `${r} min`].filter(Boolean).join(' ')
}

/** A number box you can clear and retype: the text is kept while typing, clamped when you leave. */
function LengthInput({
  label,
  value,
  max = MAX_INPUT_CHARS,
  onChange,
}: {
  label: string
  value: number
  max?: number
  onChange: (n: number) => void
}) {
  const [text, setText] = useState(String(value))
  const clamp = (raw: string) => Math.min(Math.max(Math.trunc(Number(raw)) || 1, 1), max)
  return (
    <Input
      type="number"
      min={1}
      max={max}
      aria-label={label}
      value={text}
      onChange={(e) => {
        setText(e.target.value)
        if (e.target.value !== '') onChange(clamp(e.target.value))
      }}
      onBlur={() => {
        const n = clamp(text)
        setText(String(n))
        onChange(n)
      }}
    />
  )
}

/** Settings of the selected step. Only fixed, closed operations: nothing here runs user code. */
/** What a step gives back: each field with what it means and an example, so a link can be wired by
 *  looking at it. */
function OutputList({ fields }: { fields: OutField[] }) {
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

/** The automation a "start a flow for each" step launches (never this one). */
function FlowPicker({
  node,
  patch,
}: {
  node: Extract<GraphNode, { type: 'tool' }>
  patch: (p: Partial<GraphNode>) => void
}) {
  const t = useT()
  const { flowId } = useParams()
  const flows = useFlows()
  return (
    <div className="space-y-1">
      <NativeSelect
        aria-label={t('helpers.foreach.flow')}
        value={node.flow_id ?? ''}
        onChange={(e) => patch({ flow_id: e.target.value || null } as Partial<GraphNode>)}
      >
        <option value="">{t('helpers.foreach.choose')}</option>
        {(flows.data ?? [])
          .filter((f) => f.id !== flowId)
          .map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
      </NativeSelect>
      <p className="text-xs text-muted-foreground">{t('helpers.foreach.hint')}</p>
    </div>
  )
}

export function NodeInspector({
  graph,
  node,
  title,
  avatar,
  spec,
  onGraph,
}: {
  graph: Graph
  node: GraphNode
  title: string
  avatar?: AvatarSpec
  /** The pinned spec of a helper step, for "Test this step". */
  spec?: VersionSpec
  onGraph: (g: Graph) => void
}) {
  const t = useT()
  const [testing, setTesting] = useState(false)
  const patch = (p: Partial<GraphNode>) => onGraph(patchNode(graph, node.id, p))
  const Icon = KIND[node.type].icon
  const linked = mappedInputs(graph, node.id) // a linked input is not typed here
  const agent = useAgent(node.type === 'agent' ? node.agent_id : undefined)
  return (
    <section
      aria-label={title}
      style={
        avatar
          ? ({
              '--kl': PALETTES[avatar.palette]?.accent,
              '--kd': PALETTES[avatar.palette]?.fill,
            } as React.CSSProperties)
          : undefined
      }
      className={`kind ${KIND[node.type].cls} space-y-4 rounded-xl border border-t-4 border-t-(--k) bg-card p-4`}
    >
      <header className="flex items-center gap-3">
        {avatar ? (
          <Avatar spec={avatar} size={36} />
        ) : (
          <span
            aria-hidden
            className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted"
            style={{ color: 'var(--k)' }}
          >
            <Icon className="size-4" />
          </span>
        )}
        <div className="min-w-0">
          <h2 className="truncate leading-tight font-semibold">{title}</h2>
          <p
            className="text-[11px] font-semibold tracking-wider uppercase"
            style={{ color: 'var(--k)' }}
          >
            {t(typeKey(node.type))}
          </p>
        </div>
      </header>
      {node.type === 'tool' && typeableInputs(node.tool).length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">{t('helpers.fixed.hint')}</p>
          {typeableInputs(node.tool).map((name) => (
            <div key={name} className="space-y-1">
              <Label htmlFor={`fixed-${node.id}-${name}`}>{t(`helpers.fixed.${name}`)}</Label>
              <Input
                id={`fixed-${node.id}-${name}`}
                value={node.fixed?.[name] ?? ''}
                disabled={linked.has(name)}
                maxLength={MAX_FIXED_CHARS}
                placeholder={t(`helpers.fixed.${name}.example`)}
                onChange={(e) => {
                  const fixed = { ...node.fixed, [name]: e.target.value }
                  if (!e.target.value) delete fixed[name]
                  patch({ fixed } as Partial<GraphNode>)
                }}
              />
              {linked.has(name) && (
                <p className="text-xs text-muted-foreground">{t('helpers.fixed.linked')}</p>
              )}
            </div>
          ))}
        </div>
      )}
      {(node.type === 'input' || node.type === 'output') && (
        <>
          <p className="text-xs text-muted-foreground">
            {t(node.type === 'input' ? 'helpers.inspect.input' : 'helpers.inspect.output')}
          </p>
          <Fields
            value={node.fields as FieldList}
            onChange={(fields) => patch({ fields } as Partial<GraphNode>)}
          />
        </>
      )}
      {node.type !== 'output' && (
        <OutputList
          fields={outputFields(
            node,
            node.type === 'agent' && spec ? new Map([[node.agent_version_id, spec]]) : new Map(),
          )}
        />
      )}
      {node.type === 'condition' && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">{t('helpers.inspect.condition')}</p>
          <NativeSelect
            aria-label={t('helpers.cond.op')}
            value={node.op}
            onChange={(e) => patch({ op: e.target.value } as Partial<GraphNode>)}
          >
            {(['eq', 'neq', 'contains', 'gt', 'lt'] as const).map((o) => (
              <option key={o} value={o}>
                {t(`helpers.cond.${o}`)}
              </option>
            ))}
          </NativeSelect>
          <Input
            aria-label={t('helpers.cond.value')}
            value={node.value}
            maxLength={200}
            onChange={(e) => patch({ value: e.target.value } as Partial<GraphNode>)}
          />
        </div>
      )}
      {node.type === 'tool' && (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">{t(`helpers.tool.${node.tool}.about`)}</p>
          {node.tool === 'for_each' && <FlowPicker node={node} patch={patch} />}
          {node.tool === 'wait' && (
            <div className="space-y-1">
              <p className="text-sm font-medium">{t('helpers.wait.minutes')}</p>
              <LengthInput
                label={t('helpers.wait.minutes')}
                value={node.minutes ?? 60}
                max={MAX_WAIT_MINUTES}
                onChange={(minutes) => patch({ minutes } as Partial<GraphNode>)}
              />
              <p className="text-xs text-muted-foreground">
                {t('helpers.wait.hint', { time: hoursMinutes(node.minutes ?? 60) })}
              </p>
            </div>
          )}
        </div>
      )}
      {node.type === 'transform' && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">{t('helpers.inspect.transform')}</p>
          <NativeSelect
            aria-label={t('helpers.transform.op')}
            value={node.op}
            onChange={(e) =>
              patch({
                op: e.target.value,
                arg: e.target.value === 'truncate' ? (node.arg ?? 500) : null,
              } as Partial<GraphNode>)
            }
          >
            {(['trim', 'truncate', 'lower', 'upper', 'first_line'] as const).map((o) => (
              <option key={o} value={o}>
                {t(`helpers.transform.${o}`)}
              </option>
            ))}
          </NativeSelect>
          {node.op === 'truncate' && (
            <LengthInput
              label={t('helpers.transform.arg')}
              value={node.arg ?? 500}
              onChange={(arg) => patch({ arg } as Partial<GraphNode>)}
            />
          )}
        </div>
      )}
      {node.type === 'agent' && (
        <div className="space-y-2 text-sm">
          <Link
            to={`/helpers/${node.agent_id}`}
            className="text-primary underline-offset-4 hover:underline"
          >
            {t('helpers.inspect.edit_helper')}
          </Link>
          <p className="font-mono text-xs text-muted-foreground">
            {t('helpers.id')}: {node.agent_id}
          </p>
          {agent.data && agent.data.version_id !== node.agent_version_id && (
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                patch({ agent_version_id: agent.data.version_id } as Partial<GraphNode>)
              }
            >
              {t('helpers.inspect.update_version', { version: agent.data.current_version })}
            </Button>
          )}
        </div>
      )}
      {node.type === 'agent' && spec && (
        <div className="space-y-3 border-t pt-3">
          <Button
            variant="outline"
            size="sm"
            aria-expanded={testing}
            onClick={() => setTesting((o) => !o)}
          >
            <FlaskConical data-icon="inline-start" />
            {t('helpers.live.test_step')}
            <ChevronDown
              data-icon="inline-end"
              className={`transition-transform duration-200 ${testing ? 'rotate-180' : ''}`}
            />
          </Button>
          {testing && (
            <>
              <p className="text-xs text-muted-foreground">{t('helpers.live.test_hint')}</p>
              <TryPanel agentId={node.agent_id} spec={spec} />
            </>
          )}
        </div>
      )}
    </section>
  )
}
