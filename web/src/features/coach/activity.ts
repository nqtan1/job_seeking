import { currentLang, type Key, type Vars } from '@/i18n'

export type Step = {
  id: string
  label: string
  tool?: string
  status: 'running' | 'done' | 'error'
}
type Counted = { chars?: number; truncated?: boolean; title?: string | null }
export type Context = {
  job?: Counted | null
  profile?: Counted | null
  fit?: Counted | null
  saved_jobs?: number | null
  history?: { kept?: number; dropped?: number } | null
}

type T = (key: Key, vars?: Vars) => string
const TOOLS = ['get_job', 'get_profile', 'get_fit_analysis', 'web_research'] as const

/** A live step arrives with the server's English label; the tool name picks the translation. */
export const stepLabel = (s: Step, t: T) =>
  currentLang() !== 'en' && s.tool && (TOOLS as readonly string[]).includes(s.tool)
    ? t(`coach.tool.${s.tool}` as Key)
    : s.label
export const stepsFromMeta = (
  meta: { steps?: { tool: string; status: 'done' | 'error' }[] } | null | undefined,
  t: T,
): Step[] =>
  (meta?.steps ?? []).map((s, i) => ({
    id: String(i),
    label: (TOOLS as readonly string[]).includes(s.tool)
      ? t(`coach.tool.${s.tool}` as Key)
      : s.tool,
    status: s.status,
  }))

const NOTICES = ['web_unavailable', 'step_limit', 'turn_timeout', 'tool_error']

/** The text of a notice code from the server; an unknown code is shown as it is. */
export const noticeText = (code: string, t: T) =>
  NOTICES.includes(code) ? t(`coach.notice.${code}` as Key) : code
