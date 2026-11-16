import { SearchX } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { ListSkeleton } from '@/components/Skeleton'
import { buttonVariants } from '@/components/ui/button'
import { useT } from '@/i18n'
import { toolText, useTools } from './api'

/** One tool: what it does, takes and gives. No direct run: it is used in a flow or by an agent. */
export function ToolPage() {
  const t = useT()
  const { id = '' } = useParams()
  const tools = useTools()
  const tool = tools.data?.find((x) => x.id === id && x.pack !== 'core')
  const back = { to: '/tools', label: t('nav.tools') }
  if (!tool)
    return (
      <Page title={t('nav.tools')} back={back}>
        <ErrorMessage error={tools.error} />
        {tools.isLoading ? (
          <ListSkeleton />
        ) : (
          !tools.error && <EmptyState icon={SearchX} title={t('err.not_found')} />
        )}
      </Page>
    )
  return (
    <Page
      title={toolText(t, tool.id, 'name')}
      back={back}
      actions={
        <>
          <Link to="/helpers" className={buttonVariants({ variant: 'outline' })}>
            {t('tools.give_agent')}
          </Link>
          <Link to="/automations" className={buttonVariants()}>
            {t('tools.use_flow')}
          </Link>
        </>
      }
    >
      <p>{toolText(t, tool.id, 'about')}</p>
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
        <dt className="font-medium">{t('tools.inputs')}</dt>
        <dd>
          {tool.inputs
            .map((i) => (i.required ? i.name : `${i.name} (${t('tools.optional')})`))
            .join(', ') || '—'}
        </dd>
        <dt className="font-medium">{t('tools.outputs')}</dt>
        <dd>{tool.outputs.join(', ') || '—'}</dd>
      </dl>
    </Page>
  )
}
