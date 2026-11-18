import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useProfile } from '@/features/candidate/api'
import { useChats } from '@/features/coach/api'
import { useReviews } from '@/features/cv-review/api'
import { useJobs } from '@/features/job-search/api'
import { useLetters } from '@/features/letters/api'
import { useAllFits } from '@/features/pipeline/api'
import { useRadarStatus, useSearches } from '@/features/radar/api'
import { useMe } from '@/features/settings/api'
import { useApplications } from '@/features/tracker/api'
import type { Key } from '@/i18n'
import { api } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { unwrap } from '@/lib/api/unwrap'

export type Step = { label: Key; to: string; done: boolean }
type Reminder = { key: string; label: Key; to: string; count: number }
const WEEK = 7 * 864e5

/** What needs the user today, most urgent first; a zero count is no reminder. Pure. Finished and
 *  failed runs are not here: the inbox reports them. */
export function reminders(c: { followUps: number; matches: number }): Reminder[] {
  const all: Reminder[] = [
    { key: 'follow_up', label: 'today.follow_up', to: '/tracker', count: c.followUps },
    { key: 'matches', label: 'today.matches', to: '/radar', count: c.matches },
  ]
  return all.filter((r) => r.count > 0)
}

/** Everything the dashboard shows, from lists the app already loads. */
export function useToday() {
  const me = useMe()
  const profile = useProfile() // not `me.onboarding`: that one is stale right after the first save
  const jobs = useJobs()
  const fits = useAllFits()
  const letters = useLetters()
  const apps = useApplications()
  const radars = useSearches()
  const chats = useChats()
  const review = !!me.data?.cv_review_enabled
  const reviews = useReviews(review)
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
    profile: !!profile.data,
    reminders: reminders({
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
    recent,
  }
}

type InboxItem = Pick<components['schemas']['InboxMeta'], 'kind' | 'link'> & {
  id: string
  text: string
  at: string
}

/** The newest inbox messages of the user's Assistant conversation (created on first call). */
export function useInbox() {
  const assistant = useQuery({
    queryKey: ['assistant'],
    retry: false, // 422 until the user has a CV: the inbox then stays empty, not an error
    queryFn: async () => unwrap(await api.GET('/api/v1/coach/assistant')),
  })
  const id = assistant.data?.id
  const latest = useQuery({
    queryKey: ['messages', id, 'latest'],
    enabled: !!id,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/coach/conversations/{conversation_id}/messages', {
          params: { path: { conversation_id: id ?? '' }, query: { limit: 30, latest: true } },
        }),
      ),
  })
  const items: InboxItem[] = (latest.data ?? []).flatMap((m) =>
    m.meta?.inbox
      ? [
          {
            id: m.id,
            kind: m.meta.inbox.kind,
            text: m.content,
            link: m.meta.inbox.link,
            at: m.created_at,
          },
        ]
      : [],
  )
  return { id, items: items.slice(-5).reverse() }
}
