import { z } from 'zod'
import type { Profile, ProfilePatch } from './api'

// Loose objects keep fields the form does not render (location, skills_used, gpa...) so a PATCH
// never drops them. Only what the backend does not enforce is validated here.
const req = (label: string) => z.string().trim().min(1, `${label} is required.`)
export const profileSchema = z.object({
  personal_info: z.looseObject({ name: req('Name') }),
  summary: z.string(),
  experiences: z.array(z.looseObject({ job_title: req('Job title'), company: req('Company') })),
  formations: z.array(z.looseObject({ degree: req('Degree'), institution: req('Institution') })),
  skills: z.array(z.looseObject({ name: req('Skill') })),
})
export type FormValues = z.infer<typeof profileSchema>

const nul = (v: unknown) => (typeof v === 'string' && v.trim() === '' ? null : v)
const nullEmpty = <T extends object>(o: T) =>
  Object.fromEntries(Object.entries(o).map(([k, v]) => [k, nul(v)])) as T

/** Server data → form values (null → '' so inputs stay controlled). */
export function toForm({ data }: Profile): FormValues {
  const blank = <T extends object>(o: T) =>
    Object.fromEntries(Object.entries(o).map(([k, v]) => [k, v ?? ''])) as T
  return {
    personal_info: blank(data.personal_info),
    summary: data.summary ?? '',
    experiences: data.experiences.map(blank),
    formations: data.formations.map(blank),
    skills: data.skills.map(blank),
  } as FormValues
}

/** Form values → PATCH body (empty strings back to null). */
export const toPatch = (v: FormValues): ProfilePatch =>
  ({
    personal_info: nullEmpty(v.personal_info),
    summary: nul(v.summary),
    experiences: v.experiences.map(nullEmpty),
    formations: v.formations.map(nullEmpty),
    skills: v.skills.map(nullEmpty),
  }) as ProfilePatch
