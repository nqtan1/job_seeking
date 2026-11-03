import { Copy, Trash2 } from 'lucide-react'
import { useRef } from 'react'
import { useT } from '@/i18n'
import { Avatar } from './Avatar'
import { Button } from '@/components/ui/button'
import { NativeSelect } from '@/components/ui/native-select'
import { type AvatarSpec, type Mood, PALETTES } from './avatar'
import { KIND } from './nodeKind'
import {
  type Graph,
  type Refusal,
  type Specs,
  cloneNodes,
  connect,
  orderOf,
  refusal,
  removeEdge,
  removeNode,
  resultLast,
  typeKey,
} from './graph'
import type { Selection } from './Canvas'

/** The same graph as a plain list, in execution order. It is the phone-friendly and keyboard
 *  editor: every canvas gesture (add a link, remove, duplicate) has a control here. */
export function StepsList({
  graph,
  specs,
  titles,
  avatars,
  moods,
  selection,
  readOnly,
  onGraph,
  onSelect,
  onRefuse,
}: {
  graph: Graph
  specs: Specs
  titles: ReadonlyMap<string, string>
  avatars: ReadonlyMap<string, AvatarSpec>
  moods?: ReadonlyMap<string, Mood>
  selection: Selection
  readOnly?: boolean
  onGraph?: (g: Graph) => void
  onSelect: (s: Selection) => void
  onRefuse?: (why: Refusal) => void
}) {
  const t = useT()
  const byId = new Map(graph.nodes.map((n) => [n.id, n]))
  const list = useRef<HTMLOListElement>(null)
  return (
    <ol ref={list} tabIndex={-1} aria-label={t('helpers.steps')} className="space-y-3 outline-none">
      {orderOf(graph).map((id, i) => {
        const n = byId.get(id)!
        const selected = selection?.kind === 'node' && selection.id === id
        const out = graph.edges.filter((e) => e.from.node === id)
        const targets = graph.nodes.filter(
          (m) => refusal(graph, id, n.type === 'condition' ? 'true' : 'out', m.id) === null,
        )
        const Icon = KIND[n.type].icon
        const ports = n.type === 'condition' ? (['true', 'false'] as const) : (['out'] as const)
        const av = avatars.get(id)
        const p = av ? PALETTES[av.palette] : undefined
        return (
          <li
            key={id}
            aria-current={selected || undefined}
            style={p ? ({ '--kl': p.accent, '--kd': p.fill } as React.CSSProperties) : undefined}
            className={`kind ${KIND[n.type].cls} step-node rounded-xl border border-l-4 border-l-(--k) bg-card p-3 sm:p-4`}
            data-selected={selected}
          >
            <div className="flex items-center gap-3">
              <span
                aria-label={t('helpers.flow.step_n', { n: i + 1 })}
                role="img"
                className="grid size-6 shrink-0 place-items-center rounded-full bg-muted text-xs font-semibold text-muted-foreground tabular-nums"
              >
                {i + 1}
              </span>
              {av ? (
                <Avatar spec={av} mood={moods?.get(id)} size={36} />
              ) : (
                <span
                  aria-hidden
                  className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted"
                  style={{ color: 'var(--k)' }}
                >
                  <Icon className="size-4" />
                </span>
              )}
              <button
                type="button"
                onClick={() => onSelect({ kind: 'node', id })}
                className="min-w-0 flex-1 rounded py-1 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50 pointer-coarse:min-h-11"
              >
                <span className="block truncate font-medium">{titles.get(id)}</span>
                <span className="block text-xs text-muted-foreground">{t(typeKey(n.type))}</span>
              </button>
              {!readOnly && n.type !== 'input' && n.type !== 'output' && (
                <>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`${t('helpers.duplicate')}: ${titles.get(id)}`}
                    onClick={() => onGraph?.(cloneNodes(graph, [id]))}
                  >
                    <Copy />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`${t('helpers.remove')}: ${titles.get(id)}`}
                    onClick={() => {
                      list.current?.focus() // the row is going away: keep focus in the list
                      onGraph?.(removeNode(graph, id))
                    }}
                  >
                    <Trash2 />
                  </Button>
                </>
              )}
            </div>
            {out.length > 0 && (
              <ul className="mt-3 flex flex-wrap items-center gap-1.5 pl-9">
                {out.map((e) => (
                  <li
                    key={e.id}
                    className="flex items-center rounded-full border bg-muted/60 text-xs"
                  >
                    <button
                      type="button"
                      onClick={() => onSelect({ kind: 'edge', id: e.id })}
                      aria-current={
                        (selection?.kind === 'edge' && selection.id === e.id) || undefined
                      }
                      className="rounded-full px-2.5 py-1 outline-none hover:text-primary focus-visible:ring-3 focus-visible:ring-ring/50 aria-[current]:font-semibold aria-[current]:text-primary pointer-coarse:min-h-11"
                    >
                      {e.from.port && e.from.port !== 'out'
                        ? `${t(`helpers.port.${e.from.port}`)} `
                        : ''}
                      → {titles.get(e.to)}
                    </button>
                    {!readOnly && (
                      <button
                        type="button"
                        aria-label={`${t('helpers.unlink')}: ${titles.get(e.from.node)} → ${titles.get(e.to)}`}
                        onClick={() => {
                          list.current?.focus()
                          onGraph?.(removeEdge(graph, e.id))
                        }}
                        className="min-h-6 min-w-6 rounded-full px-2 py-1 text-muted-foreground outline-none hover:text-destructive focus-visible:ring-3 focus-visible:ring-ring/50 pointer-coarse:min-h-11 pointer-coarse:min-w-11"
                      >
                        ×
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {!readOnly && n.type !== 'output' && targets.length > 0 && (
              <div className="mt-3 flex flex-wrap items-end gap-3 pl-9">
                {ports.map((port) => {
                  const label =
                    `${t('helpers.connect_to')} ${port === 'out' ? '' : t(`helpers.port.${port}`)}`.trim()
                  return (
                    <div key={port} className="space-y-1">
                      <label
                        htmlFor={`to-${id}-${port}`}
                        className="block text-xs font-medium text-muted-foreground"
                      >
                        {label}
                      </label>
                      <NativeSelect
                        id={`to-${id}-${port}`}
                        size="sm"
                        value=""
                        onChange={(e) => {
                          if (!e.target.value) return
                          const r = connect(graph, id, port, e.target.value, specs)
                          if (r.refused) onRefuse?.(r.refused)
                          else {
                            onGraph?.(r.graph)
                            if (r.edge) onSelect({ kind: 'edge', id: r.edge.id })
                          }
                        }}
                      >
                        <option value="">{t('helpers.flow.choose_step')}</option>
                        {resultLast(
                          graph,
                          targets.map((m) => m.id),
                        ).map((tid) => (
                          <option key={tid} value={tid}>
                            {titles.get(tid)}
                          </option>
                        ))}
                      </NativeSelect>
                    </div>
                  )
                })}
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}
