import { ExternalLink } from 'lucide-react'
import { StatusBadge } from '@/components/StatusBadge'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { components } from '@/lib/api/schema'

type Job = components['schemas']['JobOut']

/** Where the offer lives, for jobs that came from France Travail (the same address the search uses). */
const originalUrl = (job: Job) =>
  job.source === 'france_travail' && job.external_id
    ? `https://candidat.francetravail.fr/offres/recherche/detail/${job.external_id}`
    : null

const Bullets = ({ title, items }: { title: string; items: string[] }) =>
  items.length > 0 && (
    <div className="space-y-1">
      <p className="text-sm font-medium">{title}</p>
      <ul className="list-disc space-y-0.5 pl-5 text-sm text-muted-foreground">
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </div>
  )

/** Everything the offer says, next to the analysis: facts, skills, missions, the full text. */
export function JobDescription({ job }: { job: Job }) {
  const d = job.data
  const facts = [
    d.badges.contract_type,
    d.badges.location_full ?? d.badges.location,
    d.badges.salary,
    d.badges.experience_level,
    d.badges.remote_policy,
  ].filter(Boolean) as string[]
  const skills = [...new Set([...d.profile.technical_skills, ...d.tech_stack])]
  const url = originalUrl(job)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2">
          Job description
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className={buttonVariants({ variant: 'outline', size: 'sm' })}
            >
              <ExternalLink className="size-3.5" /> View the original offer
            </a>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {facts.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {facts.map((f) => (
              <StatusBadge key={f} tone="info">
                {f}
              </StatusBadge>
            ))}
          </div>
        )}
        {skills.length > 0 && (
          <div className="space-y-1">
            <p className="text-sm font-medium">Skills</p>
            <ul className="flex flex-wrap gap-1.5">
              {skills.map((s) => (
                <li key={s} className="rounded-full bg-muted px-2.5 py-0.5 text-xs">
                  {s}
                </li>
              ))}
            </ul>
          </div>
        )}
        <Bullets title="Missions" items={d.missions} />
        <Bullets title="Nice to have" items={d.profile.nice_to_have} />
        {d.job_description_text && (
          <div className="space-y-1">
            <p className="text-sm font-medium">Full text</p>
            <p className="max-h-96 overflow-y-auto text-sm whitespace-pre-wrap text-muted-foreground">
              {d.job_description_text}
            </p>
          </div>
        )}
        {!d.job_description_text && d.missions.length === 0 && skills.length === 0 && (
          <p className="text-sm text-muted-foreground">
            The offer has no more details here.
            {url ? ' Open the original offer for the full text.' : ''}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
