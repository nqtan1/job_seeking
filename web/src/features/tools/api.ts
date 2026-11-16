import { useQuery } from '@tanstack/react-query'
import { useMe } from '@/features/settings/api'
import { type Key, catalogs, registerMessages, type useT } from '@/i18n'
import { helpers } from '@/i18n/messages/helpers'
import { api } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { unwrap } from '@/lib/api/unwrap'

registerMessages(helpers) // the tool names live with the helpers' messages

export type Tool = components['schemas']['ToolOut']

/** The tools of the packs that are on. The endpoint lives with helpers: off means it does not exist. */
export function useTools() {
  const on = !!useMe().data?.helpers_enabled
  return useQuery({
    queryKey: ['tools'],
    enabled: on,
    staleTime: Infinity, // code, not data: it changes with a deploy
    queryFn: async () => unwrap(await api.GET('/api/v1/tools')),
  })
}

/** A tool's text, or its id when a new pack ships without one yet. */
export const toolText = (
  t: ReturnType<typeof useT>,
  id: string,
  part: 'name' | 'short' | 'about',
) => {
  const key = `helpers.tool.${id}.${part}`
  return key in catalogs.en ? t(key as Key) : part === 'name' ? id : ''
}
