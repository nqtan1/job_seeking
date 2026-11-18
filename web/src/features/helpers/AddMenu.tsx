import { Plus } from 'lucide-react'
import { useRef } from 'react'
import { useT } from '@/i18n'
import { Button } from '@/components/ui/button'
import { toolText, useTools } from '@/features/tools/api'
import { typeKey } from './graph'

/** The one "+ Add" menu: a helper, an action, a condition or a clean-text step. */
export function AddMenu({
  disabled,
  helpers,
  onHelper,
  onTool,
  onCondition,
  onTransform,
}: {
  disabled: boolean
  helpers: { id: string; name: string }[]
  onHelper: (id: string) => void
  onTool: (tool: string) => void
  onCondition: () => void
  onTransform: () => void
}) {
  const t = useT()
  const tools = useTools()
  const ref = useRef<HTMLDetailsElement>(null)
  const item =
    'block w-full rounded-lg px-2 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50'
  const head = 'px-2 pt-2 pb-1 text-xs font-medium text-muted-foreground'
  const pick = (f: () => void) => () => {
    if (ref.current) ref.current.open = false
    f()
  }
  if (disabled)
    return (
      <Button size="sm" disabled>
        <Plus data-icon="inline-start" />
        {t('helpers.flow.add')}
      </Button>
    )
  return (
    <details
      ref={ref}
      className="relative"
      onKeyDown={(e) => e.key === 'Escape' && ref.current && (ref.current.open = false)}
    >
      <summary className="inline-flex h-7 cursor-pointer list-none items-center gap-1 rounded-lg border bg-background px-2.5 text-sm font-medium outline-none select-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 pointer-coarse:h-11 [&::-webkit-details-marker]:hidden">
        <Plus aria-hidden className="size-4" />
        {t('helpers.flow.add')}
      </summary>
      <div className="absolute top-full left-0 z-20 mt-1 max-h-96 w-60 overflow-y-auto rounded-xl border bg-popover p-1 shadow-lg">
        {helpers.length > 0 && (
          <>
            <p className={head}>{t('helpers.node.agent')}</p>
            {helpers.map((a) => (
              <button
                key={a.id}
                type="button"
                className={item}
                onClick={pick(() => onHelper(a.id))}
              >
                {a.name}
              </button>
            ))}
          </>
        )}
        <p className={head}>{t('helpers.node.tool')}</p>
        {(tools.data ?? []).map(({ id }) => (
          <button key={id} type="button" className={item} onClick={pick(() => onTool(id))}>
            {toolText(t, id, 'name')}
          </button>
        ))}
        <button type="button" className={item} onClick={pick(onCondition)}>
          {t('helpers.node.condition')}
        </button>
        <button type="button" className={item} onClick={pick(onTransform)}>
          {t(typeKey('transform'))}
        </button>
      </div>
    </details>
  )
}
