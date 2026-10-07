import {
  Briefcase,
  GraduationCap,
  Globe,
  Mail,
  MapPin,
  Phone,
  Sparkles,
  UserCheck,
  Wrench,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Profile } from './api'

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join('')

const when = (a?: string | null, b?: string | null) => [a, b].filter(Boolean).join(' – ') || null

function Block({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <span className="text-primary">{icon}</span>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

/** The saved profile as readable blocks; editing is a separate mode (ProfileForm). */
export function ProfileView({ profile }: { profile: Profile }) {
  const { personal_info: p, summary, experiences, formations, skills } = profile.data
  const references = profile.data.references ?? []
  const contact = [
    { icon: <Mail className="size-4" />, text: p.email },
    { icon: <Phone className="size-4" />, text: p.phone },
    { icon: <MapPin className="size-4" />, text: p.address },
  ].filter((c) => c.text)
  const links = [p.linkedin, p.github, p.website].filter((l): l is string => !!l)

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-5">
          <div
            aria-hidden
            className="grid size-16 shrink-0 place-items-center rounded-full bg-primary/10 text-xl font-semibold text-primary"
          >
            {initials(p.name)}
          </div>
          <div className="min-w-0 flex-1 space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight">{p.name}</h2>
            <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted-foreground">
              {contact.map((c) => (
                <li key={c.text} className="flex items-center gap-1.5">
                  {c.icon}
                  {c.text}
                </li>
              ))}
              {links.map((l) => (
                <li key={l} className="flex items-center gap-1.5">
                  <Globe className="size-4" />
                  <a
                    href={/^https?:/.test(l) ? l : `https://${l}`}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="hover:text-foreground hover:underline"
                  >
                    {l.replace(/^https?:\/\/(www\.)?/, '')}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </CardContent>
      </Card>

      {summary && (
        <Block icon={<Sparkles className="size-4" />} title="About you">
          <p className="max-w-prose whitespace-pre-line text-sm leading-relaxed">{summary}</p>
        </Block>
      )}

      {skills.length > 0 && (
        <Block icon={<Wrench className="size-4" />} title="Skills">
          <ul className="flex flex-wrap gap-2">
            {skills.map((s) => (
              <li
                key={s.name}
                className="rounded-full border bg-muted/50 px-3 py-1 text-sm"
                title={s.category ?? undefined}
              >
                {s.name}
              </li>
            ))}
          </ul>
        </Block>
      )}

      {experiences.length > 0 && (
        <Block icon={<Briefcase className="size-4" />} title="Experience">
          <ol className="space-y-5 border-l pl-5">
            {experiences.map((e, i) => (
              <li key={i} className="relative space-y-1">
                <span className="absolute -left-[1.6rem] top-1.5 size-2.5 rounded-full bg-primary" />
                <p className="font-medium">
                  {e.job_title} <span className="text-muted-foreground">· {e.company}</span>
                </p>
                <p className="text-xs text-muted-foreground">
                  {[when(e.start_date, e.end_date), e.location].filter(Boolean).join(' · ')}
                </p>
                {e.description && (
                  <p className="whitespace-pre-line text-sm leading-relaxed">{e.description}</p>
                )}
              </li>
            ))}
          </ol>
        </Block>
      )}

      {formations.length > 0 && (
        <Block icon={<GraduationCap className="size-4" />} title="Education">
          <ul className="space-y-4">
            {formations.map((f, i) => (
              <li key={i} className="space-y-0.5">
                <p className="font-medium">{[f.degree, f.field].filter(Boolean).join(' · ')}</p>
                <p className="text-sm text-muted-foreground">{f.institution}</p>
              </li>
            ))}
          </ul>
        </Block>
      )}
      {references.length > 0 && (
        <Block icon={<UserCheck className="size-4" />} title="References">
          <ul className="grid gap-4 sm:grid-cols-2">
            {references.map((r, i) => (
              <li key={i} className="space-y-0.5 rounded-lg border bg-muted/30 p-3">
                <p className="font-medium">{r.name}</p>
                <p className="text-sm text-muted-foreground">
                  {[r.title, r.company].filter(Boolean).join(' · ')}
                </p>
                {r.relationship && <p className="text-xs italic">{r.relationship}</p>}
                {(r.email || r.phone) && (
                  <p className="pt-1 text-sm">{[r.email, r.phone].filter(Boolean).join(' · ')}</p>
                )}
              </li>
            ))}
          </ul>
        </Block>
      )}
    </div>
  )
}
