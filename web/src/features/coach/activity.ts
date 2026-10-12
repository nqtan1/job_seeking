export type Step = { id: string; label: string; status: 'running' | 'done' | 'error' }
type Counted = { chars?: number; truncated?: boolean; title?: string | null }
export type Context = {
  job?: Counted | null
  profile?: Counted | null
  fit?: Counted | null
  saved_jobs?: number | null
  history?: { kept?: number; dropped?: number } | null
}

const TOOL_LABELS: Record<string, string> = {
  get_job: 'Read the job',
  get_profile: 'Read your profile',
  get_fit_analysis: 'Checked the fit analysis',
  web_research: 'Searched the web',
}
export const stepsFromMeta = (
  meta: { steps?: { tool: string; status: 'done' | 'error' }[] } | null | undefined,
): Step[] =>
  (meta?.steps ?? []).map((s, i) => ({
    id: String(i),
    label: TOOL_LABELS[s.tool] ?? s.tool,
    status: s.status,
  }))

export const NOTICES: Record<string, string> = {
  web_unavailable: 'Web research is unavailable with this model.',
  step_limit: 'Reached the research step limit: answered with what was found.',
  turn_timeout: 'This took too long: answered with what was found.',
  tool_error: 'A check failed, so this answer may be less complete.',
}
