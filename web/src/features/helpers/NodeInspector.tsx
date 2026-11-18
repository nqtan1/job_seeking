import { ChevronDown, FlaskConical, Plus, X } from 'lucide-react'
import { type Dispatch, type SetStateAction, useState } from 'react'
import { Link, useParams } from 'react-router'
import { type Key, catalogs, useT } from '@/i18n'
import { toolText } from '@/features/tools/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/ui/native-select'
import { Avatar } from './Avatar'
import { useAgent, useFlows } from './api'
import { type AvatarSpec, PALETTES } from './avatar'
import {
  type Graph,
  type GraphNode,
  MAX_INPUT_CHARS,
  type VersionSpec,
  freeName,
  patchNode,
  typeKey,
  MAX_FIXED_CHARS,
  mappedInputs,
  typeableInputs,
} from './graph'
import { KIND } from './nodeKind'
import { outputFields } from './samples'
import { OutputList } from './EdgeInspector'
import { TryPanel } from './TryPanel'

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
        aria-label={t('helpers.pages.runs.flow')}
        value={node.flow_id ?? ''}
        onChange={(e) => patch({ flow_id: e.target.value || null } as Partial<GraphNode>)}
      >
        <option value="">{t('helpers.flow.choose_step')}</option>
        {(flows.data ?? [])
          .filter((f) => f.id !== flowId)
          .map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
      </NativeSelect>
    </div>
  )
}

type Of<K extends GraphNode['type']> = Extract<GraphNode, { type: K }>
type Patch = (p: Partial<GraphNode>) => void

/** Settings of the selected step. Only fixed, closed operations: nothing here runs user code. */
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
  const [testing, setTesting] = useState(false)
  const patch = (p: Partial<GraphNode>) => onGraph(patchNode(graph, node.id, p))
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
      <NodeHeader node={node} title={title} avatar={avatar} />
      {node.type === 'tool' && typeableInputs(node.tool).length > 0 && (
        <FixedInputs graph={graph} node={node} patch={patch} />
      )}
      {(node.type === 'input' || node.type === 'output') && (
        <Fields
          value={node.fields as FieldList}
          onChange={(fields) => patch({ fields } as Partial<GraphNode>)}
        />
      )}
      {node.type !== 'output' && (
        <OutputList
          fields={outputFields(
            node,
            node.type === 'agent' && spec ? new Map([[node.agent_version_id, spec]]) : new Map(),
          )}
        />
      )}
      {node.type === 'condition' && <ConditionSettings node={node} patch={patch} />}
      {node.type === 'tool' && <ToolSettings node={node} patch={patch} />}
      {node.type === 'transform' && <TransformSettings node={node} patch={patch} />}
      {node.type === 'agent' && <AgentSettings node={node} patch={patch} />}
      {node.type === 'agent' && spec && (
        <TestStep node={node} spec={spec} testing={testing} setTesting={setTesting} />
      )}
    </section>
  )
}

function NodeHeader({
  node,
  title,
  avatar,
}: {
  node: GraphNode
  title: string
  avatar?: AvatarSpec
}) {
  const t = useT()
  const Icon = KIND[node.type].icon
  return (
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
  )
}

function FixedInputs({ graph, node, patch }: { graph: Graph; node: Of<'tool'>; patch: Patch }) {
  const t = useT()
  const linked = mappedInputs(graph, node.id) // a linked input is not typed here
  return (
    <div className="space-y-2">
      {typeableInputs(node.tool).map((name) => (
        <div key={name} className="space-y-1">
          <Label htmlFor={`fixed-${node.id}-${name}`}>{t(`helpers.fixed.${name}`)}</Label>
          <Input
            id={`fixed-${node.id}-${name}`}
            value={node.fixed?.[name] ?? ''}
            disabled={linked.has(name)}
            maxLength={MAX_FIXED_CHARS}
            placeholder={
              `helpers.fixed.${name}.example` in catalogs.en
                ? t(`helpers.fixed.${name}.example` as Key)
                : undefined
            }
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
  )
}

function ConditionSettings({ node, patch }: { node: Of<'condition'>; patch: Patch }) {
  const t = useT()
  return (
    <div className="space-y-2">
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
  )
}

function ToolSettings({ node, patch }: { node: Of<'tool'>; patch: Patch }) {
  const t = useT()
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">{toolText(t, node.tool, 'about')}</p>
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
          <p className="text-xs text-muted-foreground">= {hoursMinutes(node.minutes ?? 60)}</p>
        </div>
      )}
    </div>
  )
}

function TransformSettings({ node, patch }: { node: Of<'transform'>; patch: Patch }) {
  const t = useT()
  return (
    <div className="space-y-2">
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
  )
}

function AgentSettings({ node, patch }: { node: Of<'agent'>; patch: Patch }) {
  const t = useT()
  const agent = useAgent(node.agent_id)
  return (
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
          onClick={() => patch({ agent_version_id: agent.data.version_id } as Partial<GraphNode>)}
        >
          {t('helpers.inspect.update_version', { version: agent.data.current_version })}
        </Button>
      )}
    </div>
  )
}

function TestStep({
  node,
  spec,
  testing,
  setTesting,
}: {
  node: Of<'agent'>
  spec: VersionSpec
  testing: boolean
  setTesting: Dispatch<SetStateAction<boolean>>
}) {
  const t = useT()
  return (
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
      {testing && <TryPanel agentId={node.agent_id} spec={spec} />}
    </div>
  )
}
