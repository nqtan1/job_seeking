import type { Application } from './api'

export type Attention = { app: Application; kind: 'followup' | 'interview'; days: number }

const DAY = 86_400_000
const FOLLOW_UP_AFTER_DAYS = 7
const INTERVIEW_SOON_DAYS = 3

/** What needs the user's attention now: sent a week ago with no reply, or an interview soon. */
export function needsAttention(apps: Application[], now = new Date()): Attention[] {
  const out: Attention[] = []
  for (const app of apps) {
    if (app.interview_at && app.status !== 'rejected') {
      const days = Math.ceil((new Date(app.interview_at).getTime() - now.getTime()) / DAY)
      if (days >= 0 && days <= INTERVIEW_SOON_DAYS) out.push({ app, kind: 'interview', days })
    }
    if (app.status === 'applied') {
      const sent = new Date(app.applied_at ?? app.updated_at).getTime()
      const days = Math.floor((now.getTime() - sent) / DAY)
      if (days >= FOLLOW_UP_AFTER_DAYS) out.push({ app, kind: 'followup', days })
    }
  }
  return out.sort((a, b) => (a.kind === b.kind ? 0 : a.kind === 'interview' ? -1 : 1))
}

export const practicePrompt = (app: Application) =>
  `Help me prepare for my interview at ${app.company_name}${app.job_title ? ` for the ${app.job_title} role` : ''}. Ask me the first question.`
