import { tNow } from '@/i18n'
import type { Job } from './api'

/** The employer name, or a placeholder when the model could not extract one. */
export const companyOf = (j: Job) => j.data.company.name?.trim() || tNow('jobs.company_unset')
export const jobLabel = (j: Job) => `${j.data.title} — ${companyOf(j)}`

/** What the model failed to extract, as a list: empty = nothing missing. */
export const missingOf = (j: Job) =>
  [
    !j.data.company.name?.trim() && ('company' as const),
    !j.data.company.address?.trim() && !j.data.badges.location?.trim() && ('address' as const),
  ].filter(Boolean) as ('company' | 'address')[]
