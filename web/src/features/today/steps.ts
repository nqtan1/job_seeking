import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useProfile } from '@/features/candidate/api'
import { useConversations } from '@/features/coach/api'
import { useReviews } from '@/features/cv-review/api'
import { useJobs } from '@/features/job-search/api'
import { useLetters } from '@/features/letters/api'
import { useAllFits } from '@/features/pipeline/api'
import { useRadarStatus, useSearches } from '@/features/radar/api'
import { useMe } from '@/features/settings/api'
import { useApplications } from '@/features/tracker/api'
import type { Key } from '@/i18n'
import { api } from '@/lib/api/client'
import { unwrap } from '@/lib/api/unwrap'

export type Step = { label: Key; to: string; done: boolean }
type Reminder = { key: string; label: Key; to: string; count: number }
const WEEK = 7 * 864e5

/** What needs the user today, most urgent first; a zero count is no reminder. Pure. */
export function reminders(c: { failed: number; followUps: number; matches: number }): Reminder[] {
  const all: Reminder[] = [
    { key: 'failed', label: 'today.failed', to: '/activity', count: c.failed },
    { key: 'follow_up', label: 'today.follow_up', to: '/tracker', count: c.followUps },
    { key: 'matches', label: 'today.matches', to: '/radar', count: c.matches },
  ]
  return all.filter((r) => r.count > 0)
}

/** Everything the dashboard shows, from lists the app already loads (plus the last flow runs). */
export function useToday() {
  const me = useMe()
  const profile = useProfile() // not `me.onboarding`: that one is stale right after the first save
  const jobs = useJobs()
  const fits = useAllFits()
  const letters = useLetters()
  const apps = useApplications()
  const radars = useSearches()
  const chats = useConversations()
  const review = !!me.data?.cv_review_enabled
  const reviews = useReviews(review)
  const runs = useQuery({
    queryKey: ['helper-runs', 'home'], // under the runs key: refreshed with them
    enabled: !!me.data?.helpers_enabled,
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/flow-runs', { params: { query: { limit: 5 } } })),
  })
  const matches = useRadarStatus().data?.new_matches ?? 0
  const [now] = useState(Date.now) // once per visit: render stays pure
  const has = (q: { data?: unknown[] }) => (q.data?.length ?? 0) > 0
  const steps: Step[] = [
    { label: 'pipeline.step.cv', to: '/profile', done: !!profile.data },
    ...(review
      ? [{ label: 'pipeline.step.review' as Key, to: '/cv-review', done: has(reviews) }]
      : []),
    { label: 'pipeline.step.job', to: '/jobs', done: has(jobs) },
    { label: 'pipeline.step.fit', to: '/jobs', done: has(fits) },
    { label: 'pipeline.step.letter', to: '/letters', done: has(letters) },
    { label: 'pipeline.step.track', to: '/tracker', done: has(apps) },
    { label: 'pipeline.step.radar', to: '/radar', done: has(radars) },
  ]
  const list = apps.data ?? []
  const count = (...s: string[]) => list.filter((a) => s.includes(a.status)).length
  const recent =
    [
    ...(chats.data ?? []).map((c) => ({
      key: `c${c.id}`, to: `/chat/${c.id}`, kind: 'chat' as const,
      text: c.title ?? '', at: c.updated_at,
    })),
    ...(letters.data ?? []).map((l) => ({
      key: `l${l.id}`, to: `/letters/${l.id}`, kind: 'letter' as const,
      text: l.content.subject ?? '', at: l.updated_at,
    })),
    ...(reviews.data ?? []).map((r) => ({
      key: `r${r.id}`, to: `/cv-review/${r.id}`, kind: 'review' as const,
      text: `${Math.round(r.score)}/100`, at: r.created_at,
    })),
  ] // prettier-ignore
      .sort((a, b) => b.at.localeCompare(a.at))
      .slice(0, 5)
  return {
    loading: [me, profile, jobs, fits, letters, apps, radars].some((q) => q.isPending),
    steps,
    todo: steps.find((s) => !s.done),
    reminders: reminders({
      failed: (runs.data ?? []).filter(
        (r) => r.status === 'failed' && now - Date.parse(r.created_at) < 864e5,
      ).length,
      followUps: list.filter(
        (a) => a.status === 'applied' && a.applied_at && now - Date.parse(a.applied_at) > WEEK,
      ).length,
      matches,
    }),
    stats: [
      { label: 'today.saved' as Key, to: '/jobs', value: jobs.data?.length ?? 0 },
      { label: 'today.applied' as Key, to: '/tracker', value: list.length - count('to_apply') },
      { label: 'today.interviews' as Key, to: '/tracker', value: count('interview', 'offer') },
    ],
    runs: runs.data ?? [],
    recent,
  }
}
