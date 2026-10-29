export type Range = 'all' | 'today' | '7' | '30'
export const RANGES: Range[] = ['all', 'today', '7', '30']
export type Chip = '' | 'fit' | 'letter' | 'applied' | 'interview'

const SUFFIX = /\s(sa|sas|sarl|inc|group|groupe)$/
// France Travail's stand-in for a hidden employer: never a real company.
const PLACEHOLDERS = new Set(['entreprise non divulguee'])

/** Merge key for an employer name, or null when unknown. Only TRAILING legal words are dropped. */
export function companyKey(name: string | null | undefined): string | null {
  let n = (name ?? '')
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/\./g, '')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
  if (!n || PLACEHOLDERS.has(n)) return null
  while (SUFFIX.test(n)) n = n.replace(SUFFIX, '')
  return n
}

/** Whole local calendar days between `iso` and `now` (0 = today). */
export function daysAgo(iso: string, now = new Date()): number {
  const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  return Math.round((start(now) - start(new Date(iso))) / 86_400_000)
}

export function inRange(iso: string, range: Range, now = new Date()): boolean {
  if (range === 'all') return true
  const d = daysAgo(iso, now)
  return range === 'today' ? d <= 0 : d < Number(range)
}

export type DayBucket = 'today' | 'yesterday' | 'week' | 'month' | 'earlier'
export const DAY_BUCKETS: DayBucket[] = ['today', 'yesterday', 'week', 'month', 'earlier']
export function dayBucket(iso: string, now = new Date()): DayBucket {
  const d = daysAgo(iso, now)
  return d <= 0 ? 'today' : d === 1 ? 'yesterday' : d <= 7 ? 'week' : d <= 30 ? 'month' : 'earlier'
}

/** Furthest step reached: 0 saved, 1 fit checked, 2 letter, 3 applied, 4 interview. */
export function stageOf(hasFit: boolean, hasLetter: boolean, status?: string): number {
  if (status === 'interview' || status === 'offer') return 4
  if (status && status !== 'to_apply') return 3
  return hasLetter ? 2 : hasFit ? 1 : 0
}

/** Stable 0-359 hue for an avatar colour. */
export function hue(s: string): number {
  let h = 0
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360
  return h
}

export function initials(name: string): string {
  const w = name
    .replace(/\(.*\)/, '')
    .trim()
    .split(/\s+/)
  return (w.length === 1 ? w[0].slice(0, 2) : w[0][0] + w[1][0]).toUpperCase()
}
