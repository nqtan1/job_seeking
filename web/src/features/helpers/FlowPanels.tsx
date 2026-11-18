import { CircleAlert, CircleCheck, TriangleAlert } from 'lucide-react'
import { type Key, catalogs, useT } from '@/i18n'
import { Avatar } from './Avatar'
import type { Handoff } from './api'
import type { AvatarSpec } from './avatar'
import type { Graph, Issue } from './graph'
import type { Selection } from './Canvas'
import { KIND } from './nodeKind'

export { EdgeInspector } from './EdgeInspector'
export { NodeInspector } from './NodeInspector'

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
                  {t(
                    (`helpers.issue.${i.code}` in catalogs.en
                      ? `helpers.issue.${i.code}`
                      : 'helpers.issue.generic') as Key,
                  )}
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
