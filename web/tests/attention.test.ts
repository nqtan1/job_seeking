import { isStale, postingAgeDays } from '@/features/job-search/age'
import { needsAttention } from '@/features/tracker/attention'
import type { Application } from '@/features/tracker/api'

const base = {
  id: 'a',
  company_name: 'Acme',
  status: 'applied',
  applied_at: null,
  updated_at: '2026-10-01T10:00:00Z',
  interview_at: null,
} as unknown as Application
const make = (over: Partial<Application>): Application => ({ ...base, ...over })
const now = new Date('2026-10-10T10:00:00Z')

test('flags an application with no reply after 7 days and an interview within 3 days', () => {
  const quiet = make({ id: 'quiet', updated_at: '2026-10-02T10:00:00Z' })
  const recent = make({ id: 'recent', updated_at: '2026-10-08T10:00:00Z' })
  const soon = make({ id: 'soon', status: 'interview', interview_at: '2026-10-12T09:00:00Z' })
  const far = make({ id: 'far', status: 'interview', interview_at: '2026-10-20T09:00:00Z' })
  const rejected = make({ ...soon, id: 'rejected', status: 'rejected' })
  const silent = make({ id: 'silent', updated_at: '2026-09-18T10:00:00Z' })

  const out = needsAttention([quiet, recent, soon, far, rejected, silent], now)

  expect(out.map((i) => [i.app.id, i.kind])).toEqual([
    ['soon', 'interview'],
    ['quiet', 'followup'],
    ['silent', 'ghost'], // 21+ days: offer 'Mark as ghosted'
  ])
})

test('posting age: unknown stays quiet, 30+ days is flagged as possibly stale', () => {
  const t = new Date('2026-10-10T10:00:00Z')
  expect(postingAgeDays(null, t)).toBeNull()
  expect(isStale(postingAgeDays('2026-10-05', t))).toBe(false)
  expect(isStale(postingAgeDays('2026-08-01', t))).toBe(true)
})
