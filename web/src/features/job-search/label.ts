import type { Job } from './api'

/** The employer name, or a placeholder when the model could not extract one. */
export const companyOf = (j: Job) => j.data.company.name?.trim() || 'Company not set'
export const jobLabel = (j: Job) => `${j.data.title} — ${companyOf(j)}`

/** What the model failed to extract, as a list: empty = nothing missing. */
export const missingOf = (j: Job) =>
  [
    !j.data.company.name?.trim() && 'company',
    !j.data.company.address?.trim() && !j.data.badges.location?.trim() && 'address',
  ].filter(Boolean) as string[]
