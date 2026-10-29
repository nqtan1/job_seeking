import { EmptyState } from '@/components/EmptyState'
import { ErrorMessage } from '@/components/ErrorMessage'
import { ListSkeleton } from '@/components/Skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { ApplyActions } from '@/features/pipeline/ApplyActions'
import { usePipeline } from '@/features/pipeline/api'
import { useRadarJobIds } from '@/features/radar/api'
import { sourceLabel, STATUS_KEY } from '@/features/tracker/constants'
import { Briefcase, ChevronRight, SearchX, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { Button, buttonVariants } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { useI18n, type Key } from '@/i18n'
import { cn } from 'cn'
import { DeleteJobButton } from './DeleteJobButton'
import { JobDetailsFix } from './JobDetailsFix'
import { isStale, postingAgeDays } from './age'
import { useJobs, type Job } from './api'
import {
  companyKey,
  dayBucket,
  DAY_BUCKETS,
  daysAgo,
  hue,
  initials,
  inRange,
  RANGES,
  stageOf,
  type Chip,
  type Range,
} from './group'
import { companyOf } from './label'

const VERDICT_TONE = { go: 'success', maybe: 'warning', no_go: 'danger' } as const
const GROUPS = ['none', 'employer', 'day', 'stage'] as const
type Group = (typeof GROUPS)[number]
type Sort = 'new' | 'fit'
type View = { name: string; group: Group; range: Range; sort: Sort; chip: Chip; q: string }

const STAGE_KEYS: Key[] = [
  'jobs.stage_saved',
  'jobs.stage_fit',
  'jobs.stage_letter',
  'jobs.stage_applied',
  'jobs.stage_interview',
]
const DAY_KEYS = {
  today: 'jobs.day_today',
  yesterday: 'jobs.day_yesterday',
  week: 'jobs.day_week',
  month: 'jobs.day_month',
  earlier: 'jobs.day_earlier',
} as const
const CHIPS: { id: Chip; key: Key }[] = [
  { id: '', key: 'jobs.chip_total' },
  { id: 'fit', key: 'jobs.chip_fit' },
  { id: 'letter', key: 'jobs.chip_letter' },
  { id: 'applied', key: 'jobs.chip_applied' },
  { id: 'interview', key: 'jobs.chip_interview' },
]
const DEFAULT_VIEWS: { name: Key; v: Omit<View, 'name'> }[] = [
  {
    name: 'jobs.view_everything',
    v: { group: 'employer', range: 'all', sort: 'new', chip: '', q: '' },
  },
  { name: 'jobs.view_week', v: { group: 'day', range: '7', sort: 'new', chip: '', q: '' } },
]
const DOT = ['bg-muted-foreground/50', 'bg-warning', 'bg-warning', 'bg-success', 'bg-success']

// localStorage can throw (private mode, blocked data): the page must work without it.
const load = <T,>(key: string, fallback: T): T => {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}
const save = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* not persisted */
  }
}

type Entry = {
  job: Job
  fit: ReturnType<ReturnType<typeof usePipeline>['fit']>
  letters: ReturnType<ReturnType<typeof usePipeline>['letters']>
  appStatus?: string
  stage: number
}
type Bucket = { key: string; label: string; avatar: string | null; items: Entry[] }

const placeOf = (j: Job) => j.data.badges.location?.trim() || j.data.company.address?.trim() || ''

export function JobList() {
  const { t } = useI18n()
  const jobs = useJobs()
  if (jobs.isPending) return <ListSkeleton />
  if (jobs.isError) return <ErrorMessage error={jobs.error} />
  if (jobs.data.length === 0)
    return (
      <EmptyState
        icon={Briefcase}
        title={t('jobs.empty_title')}
        description={t('jobs.empty_desc')}
      />
    )
  return <JobListBody jobs={jobs.data} />
}

function JobListBody({ jobs }: { jobs: Job[] }) {
  const { t, locale } = useI18n()
  const pipeline = usePipeline()
  const [group, setGroupState] = useState<Group>(() => {
    const g = load<string>('jobs-group', 'employer')
    return (GROUPS as readonly string[]).includes(g) ? (g as Group) : 'employer'
  })
  const [range, setRange] = useState<Range>('all')
  const [sort, setSort] = useState<Sort>('new')
  const [chip, setChip] = useState<Chip>('')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [custom, setCustom] = useState<View[]>(() => load('jobs-views', []))
  const [naming, setNaming] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)

  const setGroup = (g: Group) => {
    setGroupState(g)
    save('jobs-group', g)
  }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return
      if (e.key === '/') {
        e.preventDefault()
        searchRef.current?.focus()
      } else if (e.key === 'g') setGroup(GROUPS[(GROUPS.indexOf(group) + 1) % GROUPS.length])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [group])

  const all: Entry[] = jobs.map((job) => {
    const fit = pipeline.fit(job.id)
    const letters = pipeline.letters(job.id)
    const appStatus = pipeline.application(job.id)?.status
    return { job, fit, letters, appStatus, stage: stageOf(!!fit, letters.length > 0, appStatus) }
  })
  const needle = q.trim().toLowerCase()
  const chipOk = (e: Entry) =>
    chip === ''
      ? true
      : chip === 'fit'
        ? !e.fit
        : chip === 'letter'
          ? !!e.fit && e.letters.length === 0
          : chip === 'applied'
            ? e.stage >= 3
            : e.stage === 4
  const byDate = (a: Entry, b: Entry) => b.job.created_at.localeCompare(a.job.created_at)
  const rows = all
    .filter(
      (e) =>
        inRange(e.job.created_at, range) &&
        chipOk(e) &&
        (!needle ||
          [e.job.data.title, e.job.data.company.name, placeOf(e.job)]
            .join(' ')
            .toLowerCase()
            .includes(needle)),
    )
    .sort(
      sort === 'fit'
        ? (a, b) => (b.fit?.score ?? -1) - (a.fit?.score ?? -1) || byDate(a, b)
        : byDate,
    )

  const buckets: Bucket[] = []
  if (group === 'none') buckets.push({ key: 'all', label: '', avatar: null, items: rows })
  else {
    const map = new Map<string, Bucket>()
    for (const e of rows) {
      const ck = companyKey(e.job.data.company.name)
      const k =
        group === 'employer'
          ? (ck ?? '~unknown')
          : group === 'day'
            ? dayBucket(e.job.created_at)
            : String(e.stage)
      let b = map.get(k)
      if (!b) {
        const label =
          group === 'employer'
            ? ck
              ? companyOf(e.job)
              : t('jobs.unknown_employer')
            : group === 'day'
              ? t(DAY_KEYS[k as keyof typeof DAY_KEYS])
              : t(STAGE_KEYS[Number(k)])
        b = { key: k, label, avatar: group === 'employer' ? (ck ?? '~unknown') : null, items: [] }
        map.set(k, b)
      }
      // Shortest spelling of the name reads best ("Thales" over "THALES SA").
      if (group === 'employer' && ck && companyOf(e.job).length < b.label.length)
        b.label = companyOf(e.job)
      b.items.push(e)
    }
    buckets.push(...map.values())
    if (group === 'day')
      buckets.sort(
        (a, b) => DAY_BUCKETS.indexOf(a.key as never) - DAY_BUCKETS.indexOf(b.key as never),
      )
    if (group === 'stage') buckets.sort((a, b) => Number(b.key) - Number(a.key))
  }
  // Many groups: open only the first 3 so the list stays scannable.
  const isOpen = (b: Bucket, i: number) => open[`${group}:${b.key}`] ?? (rows.length <= 20 || i < 3)

  const state = { group, range, sort, chip, q }
  const sameView = (v: Omit<View, 'name'>) =>
    (Object.keys(state) as (keyof typeof state)[]).every((k) => state[k] === v[k])
  const apply = (v: Omit<View, 'name'>) => {
    setGroup(v.group)
    setRange(v.range)
    setSort(v.sort)
    setChip(v.chip)
    setQ(v.q)
  }
  const addView = (name: string) => {
    const next = [...custom.filter((v) => v.name !== name), { name, ...state }]
    setCustom(next)
    save('jobs-views', next)
    setNaming(false)
  }
  const removeView = (name: string) => {
    const next = custom.filter((v) => v.name !== name)
    setCustom(next)
    save('jobs-views', next)
  }
  const filtered = range !== 'all' || chip !== '' || needle !== ''
  const clear = () => {
    setRange('all')
    setChip('')
    setQ('')
  }
  const count = (f: (e: Entry) => boolean) => all.filter(f).length
  const chipCount: Record<Chip, number> = {
    '': all.length,
    fit: count((e) => !e.fit),
    letter: count((e) => !!e.fit && e.letters.length === 0),
    applied: count((e) => e.stage >= 3),
    interview: count((e) => e.stage === 4),
  }
  const pill = 'rounded-full'

  return (
    <div className="space-y-3">
      <div role="group" aria-label={t('jobs.chips_label')} className="flex flex-wrap gap-1.5">
        {CHIPS.map((c) => (
          <Button
            key={c.id}
            size="sm"
            variant="outline"
            className={pill}
            aria-pressed={chip === c.id}
            onClick={() => setChip(chip === c.id ? '' : c.id)}
          >
            <b>{chipCount[c.id]}</b> {t(c.key)}
          </Button>
        ))}
      </div>

      <div
        className="flex flex-wrap items-center gap-1.5"
        role="group"
        aria-label={t('jobs.views')}
      >
        <span className="text-xs text-muted-foreground">{t('jobs.views')}</span>
        {DEFAULT_VIEWS.map((d) => (
          <Button
            key={d.name}
            size="xs"
            variant="outline"
            className={pill}
            aria-pressed={sameView(d.v)}
            onClick={() => apply(d.v)}
          >
            {t(d.name)}
          </Button>
        ))}
        {custom.map((v) => (
          <span key={v.name} className="inline-flex items-center">
            <Button
              size="xs"
              variant="outline"
              className={cn(pill, 'rounded-r-none')}
              aria-pressed={sameView(v)}
              onClick={() => apply(v)}
            >
              {v.name}
            </Button>
            <Button
              size="icon-xs"
              variant="outline"
              className="rounded-l-none rounded-r-full"
              aria-label={t('jobs.remove_view', { name: v.name })}
              onClick={() => removeView(v.name)}
            >
              <X />
            </Button>
          </span>
        ))}
        {naming ? (
          <Input
            autoFocus
            className="h-6 w-40 text-xs"
            aria-label={t('jobs.view_name')}
            placeholder={t('jobs.view_name')}
            onBlur={() => setNaming(false)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setNaming(false)
              if (e.key === 'Enter' && e.currentTarget.value.trim())
                addView(e.currentTarget.value.trim())
            }}
          />
        ) : (
          <Button size="xs" variant="ghost" onClick={() => setNaming(true)}>
            {t('jobs.save_view')}
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          ref={searchRef}
          type="search"
          className="w-full sm:w-64"
          aria-label={t('jobs.filter_label')}
          placeholder={t('jobs.filter_placeholder')}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Escape' && setQ('')}
        />
        <div role="group" aria-label={t('jobs.group_by')} className="flex items-center gap-1">
          <span className="text-xs text-muted-foreground">{t('jobs.group_by')}</span>
          {GROUPS.map((g) => (
            <Button
              key={g}
              size="xs"
              variant="outline"
              aria-pressed={group === g}
              onClick={() => setGroup(g)}
            >
              {t(`jobs.group_${g}`)}
            </Button>
          ))}
        </div>
        <NativeSelect
          size="sm"
          aria-label={t('jobs.range_label')}
          value={range}
          onChange={(e) => setRange(e.target.value as Range)}
        >
          {RANGES.map((r) => (
            <option key={r} value={r}>
              {t('jobs.range_label')}: {t(`jobs.range_${r}`)}
            </option>
          ))}
        </NativeSelect>
        <Button
          size="sm"
          variant="outline"
          aria-pressed={sort === 'fit'}
          onClick={() => setSort(sort === 'fit' ? 'new' : 'fit')}
        >
          {sort === 'fit' ? t('jobs.newest_first') : t('jobs.best_first')}
        </Button>
      </div>
      <p aria-live="polite" className="text-xs text-muted-foreground">
        {t('jobs.shown', { shown: rows.length, total: all.length })}
      </p>

      {rows.length === 0 ? (
        <EmptyState
          icon={SearchX}
          title={t('jobs.no_match')}
          description={t('jobs.no_match_desc')}
          action={
            filtered && (
              <Button size="sm" variant="outline" onClick={clear}>
                {t('jobs.clear_filters')}
              </Button>
            )
          }
        />
      ) : (
        <ul
          className="max-h-[min(28rem,55vh)] xl:max-h-[calc(100vh-18rem)] space-y-2 overflow-y-auto rounded-xl border bg-muted/30 p-2"
          aria-label={t('jobs.your_jobs')}
        >
          {buckets.map((b, i) => {
            // A lone job under an employer needs no header; day/stage headers are the label.
            if (group === 'none' || (group === 'employer' && b.items.length === 1))
              return b.items.map((e) => (
                <JobRow key={e.job.id} e={e} showCompany={true} locale={locale} />
              ))
            const expanded = isOpen(b, i)
            const id = `jobs-group-${group}-${b.key.replace(/\W/g, '_')}`
            const applied = b.items.filter((e) => e.stage >= 3).length
            const newest = b.items.reduce(
              (m, e) => (e.job.created_at > m ? e.job.created_at : m),
              '',
            )
            const d = daysAgo(newest)
            return (
              <li key={b.key} className="space-y-2">
                <button
                  type="button"
                  aria-expanded={expanded}
                  aria-controls={id}
                  onClick={() => setOpen({ ...open, [`${group}:${b.key}`]: !expanded })}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  <ChevronRight
                    className={cn('size-4 shrink-0 transition-transform', expanded && 'rotate-90')}
                    aria-hidden
                  />
                  {b.avatar && (
                    <span
                      aria-hidden
                      style={{ '--h': hue(b.avatar) } as React.CSSProperties}
                      className="grid size-7 shrink-0 place-items-center rounded-md bg-[hsl(var(--h)_70%_50%/0.18)] text-xs font-semibold text-[hsl(var(--h)_60%_32%)] dark:text-[hsl(var(--h)_70%_78%)]"
                    >
                      {b.avatar === '~unknown' ? '?' : initials(b.label)}
                    </span>
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate font-medium">{b.label}</span>
                      <StatusBadge>{b.items.length}</StatusBadge>
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {t('jobs.newest', {
                        when:
                          d <= 0
                            ? t('jobs.when_today')
                            : d === 1
                              ? t('jobs.when_yesterday')
                              : new Date(newest).toLocaleDateString(locale),
                      })}
                      {applied > 0 && ` · ${t('jobs.n_applied', { count: applied })}`}
                    </span>
                  </span>
                  <span className="flex shrink-0 gap-0.5" aria-hidden>
                    {b.items.map((e) => (
                      <i key={e.job.id} className={cn('size-2 rounded-full', DOT[e.stage])} />
                    ))}
                  </span>
                </button>
                {expanded && (
                  <ul id={id} className="space-y-2 pl-2 sm:pl-4">
                    {b.items.map((e) => (
                      <JobRow
                        key={e.job.id}
                        e={e}
                        showCompany={group !== 'employer'}
                        locale={locale}
                      />
                    ))}
                  </ul>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function JobRow({ e, showCompany, locale }: { e: Entry; showCompany: boolean; locale: string }) {
  const { t } = useI18n()
  const fromRadar = useRadarJobIds()
  const [open, setOpen] = useState(false)
  const { job: j, fit, letters, appStatus } = e
  const meta = [showCompany ? companyOf(j) : '', placeOf(j)].filter(Boolean).join(' · ')
  const posted = postingAgeDays(j.data.source_meta.posted_on)
  const id = `job-row-${j.id}`
  return (
    <li className="rounded-xl border bg-card shadow-xs">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 rounded-xl p-3 text-left focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <span
          role="img"
          aria-label={t('jobs.stage_aria', { stage: t(STAGE_KEYS[e.stage]) })}
          className="flex shrink-0 gap-0.5"
        >
          {STAGE_KEYS.map((k, i) => (
            <i
              key={k}
              className={cn('h-1.5 w-3 rounded-full', i <= e.stage ? 'bg-primary' : 'bg-muted')}
            />
          ))}
        </span>
        <span className="min-w-0 flex-1">
          <span className="line-clamp-2 font-medium">{j.data.title}</span>
          {meta && <span className="block truncate text-sm text-muted-foreground">{meta}</span>}
        </span>
        <span className="flex shrink-0 flex-col items-end gap-1 sm:flex-row sm:items-center sm:gap-2">
          {fit ? (
            <StatusBadge tone={VERDICT_TONE[fit.data.recommendation as keyof typeof VERDICT_TONE]}>
              {t('jobs.fit_pct', { score: Math.round(fit.score) })}
            </StatusBadge>
          ) : (
            <StatusBadge>{t('jobs.fit_unchecked')}</StatusBadge>
          )}
          {fromRadar.has(j.id) && <StatusBadge tone="success">{t('jobs.from_radar')}</StatusBadge>}
          {appStatus && (
            <StatusBadge tone="success">
              {t('jobs.tracked', { status: t(STATUS_KEY[appStatus as keyof typeof STATUS_KEY]) })}
            </StatusBadge>
          )}
          <span className="text-xs text-muted-foreground">
            {new Date(j.created_at).toLocaleDateString(locale)}
          </span>
        </span>
      </button>
      {open && (
        <div id={id} className="space-y-3 border-t px-3 pt-3 pb-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone="info">{sourceLabel(t, j.source)}</StatusBadge>
            {isStale(posted) && (
              <StatusBadge tone="warning">{t('jobs.stale', { days: posted ?? 0 })}</StatusBadge>
            )}
            <StatusBadge tone={letters.length ? 'success' : 'neutral'}>
              {letters.length ? t('jobs.letters', { count: letters.length }) : t('jobs.no_letter')}
            </StatusBadge>
          </div>
          <JobDetailsFix job={j} />
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/jobs/${j.id}/fit`}
              className={buttonVariants({ variant: fit ? 'outline' : 'default', size: 'sm' })}
            >
              {fit ? t('jobs.fit_report') : t('jobs.check_fit')}
            </Link>
            <Link
              to={letters[0] ? `/letters/${letters[0].id}` : `/letters?job=${j.id}`}
              className={buttonVariants({ variant: 'outline', size: 'sm' })}
            >
              {letters[0] ? t('jobs.open_letter') : t('jobs.write_letter')}
            </Link>
            <Link
              to={`/?job=${j.id}`}
              className={buttonVariants({ variant: 'outline', size: 'sm' })}
            >
              {t('jobs.discuss')}
            </Link>
            <ApplyActions
              jobId={j.id}
              jobSource={j.source}
              pdfDocumentId={letters[0]?.pdf_document_id}
            />
            <DeleteJobButton id={j.id} title={j.data.title} />
          </div>
        </div>
      )}
    </li>
  )
}
