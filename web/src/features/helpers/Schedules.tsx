import { CalendarClock, Pause, Play, Plus, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { type Key, useI18n } from '@/i18n'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Modal } from '@/components/Modal'
import { Spinner } from '@/components/Spinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/ui/native-select'
import { Textarea } from '@/components/ui/textarea'
import {
  type FlowDetail,
  type Schedule,
  useCreateSchedule,
  useDeleteSchedule,
  useSchedules,
  useSetScheduleEnabled,
} from './api'
import { type Graph, MAX_INPUT_CHARS, type Specs, aiCalls, MAX_SCHEDULES } from './graph'
import { ChoiceCard, JobSelect, SectionCard } from './ui'

const CADENCES = ['hourly', 'daily', 'weekly'] as const
const ZONES = [
  'Europe/Paris',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Madrid',
  'Europe/Rome',
  'Europe/Brussels',
  'Africa/Casablanca',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Toronto',
  'America/Montreal',
  'Asia/Ho_Chi_Minh',
  'Asia/Bangkok',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney',
]

const detectZone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

/** "Europe/Paris" -> "Paris": people know their city, not the identifier. */
const city = (zone: string) => (zone.split('/').pop() ?? zone).replaceAll('_', ' ')

/** The name of a weekday (0 = Monday) in the interface language. */
const dayName = (day: number, locale: string) =>
  new Intl.DateTimeFormat(locale, { weekday: 'long', timeZone: 'UTC' }).format(
    new Date(Date.UTC(2024, 0, 1 + day)),
  )

type When = {
  cadence: Schedule['cadence']
  at_time?: string | null
  weekday?: number | null
  timezone: string
}

/** "Every day at 08:00 (Paris time)". */
function useSentence() {
  const { t, locale } = useI18n()
  return (s: When) => {
    if (s.cadence === 'hourly') return t('helpers.pages.sched.hourly')
    const vars = { time: s.at_time ?? '', zone: city(s.timezone) }
    return s.cadence === 'daily'
      ? t('helpers.pages.sched.daily', vars)
      : t('helpers.pages.sched.weekly', { ...vars, day: dayName(s.weekday ?? 0, locale) })
  }
}

function ScheduleRow({ s }: { s: Schedule }) {
  const { t, locale } = useI18n()
  const sentence = useSentence()
  const toggle = useSetScheduleEnabled()
  const remove = useDeleteSchedule()
  const what = sentence(s)
  const next = new Date(s.next_run_at).toLocaleString(locale, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
  const why: Key | null = s.enabled
    ? null
    : s.paused_reason === 'failures'
      ? 'helpers.pages.sched.paused_failures'
      : s.paused_reason === 'inactive'
        ? 'helpers.pages.sched.paused_inactive'
        : 'helpers.pages.sched.paused_manual'
  return (
    <li className="space-y-2 rounded-xl border bg-background p-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1 basis-48">
          <p className="font-medium">{what}</p>
          {s.enabled && (
            <p className="text-sm text-muted-foreground">
              {t('helpers.pages.sched.next', { when: next })}
            </p>
          )}
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={toggle.isPending}
          aria-label={t(
            s.enabled ? 'helpers.pages.sched.pause_label' : 'helpers.pages.sched.resume_label',
            { what },
          )}
          onClick={() => toggle.mutate({ id: s.id, enabled: !s.enabled })}
        >
          {s.enabled ? <Pause data-icon="inline-start" /> : <Play data-icon="inline-start" />}
          {t(s.enabled ? 'helpers.pages.sched.pause' : 'helpers.pages.sched.resume')}
        </Button>
        <ConfirmButton
          variant="ghost"
          label={t('helpers.pages.sched.delete')}
          aria-label={t('helpers.pages.sched.delete_label', { what })}
          confirmLabel={t('helpers.pages.sched.delete_confirm')}
          confirmAriaLabel={t('helpers.pages.sched.delete_label', { what })}
          cancelLabel={t('helpers.cancel')}
          pending={remove.isPending}
          onConfirm={(reset) => remove.mutate(s.id, { onSettled: reset })}
        />
      </div>
      {why && <p className="rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning">{t(why)}</p>}
      <ErrorMessage error={toggle.error ?? remove.error} />
    </li>
  )
}

/** "Run it by itself" card of the flow editor: list, add, pause and delete schedules. `dirty` is
 *  true while the editor has changes that are not saved (a schedule runs the saved version). */
export function SchedulePanel({
  flow,
  graph,
  specs,
  dirty = false,
}: {
  flow: FlowDetail
  graph: Graph
  specs: Specs
  dirty?: boolean
}) {
  const { t } = useI18n()
  const schedules = useSchedules(flow.id)
  const [adding, setAdding] = useState(false)
  const blocked = dirty
    ? 'helpers.pages.sched.dirty'
    : flow.issues.some((i) => i.severity === 'error')
      ? 'helpers.pages.sched.issues'
      : null
  const rows = schedules.data ?? []
  return (
    <SectionCard
      icon={CalendarClock}
      title={t('helpers.pages.sched.title')}
      help={t('helpers.pages.sched.help')}
    >
      <ErrorMessage error={schedules.error} />
      {schedules.isPending ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('helpers.pages.sched.none')}</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((s) => (
            <ScheduleRow key={s.id} s={s} />
          ))}
        </ul>
      )}
      {blocked && <p className="rounded-lg bg-muted px-3 py-2 text-sm">{t(blocked)}</p>}
      <Button disabled={!!blocked} onClick={() => setAdding(true)}>
        <Plus data-icon="inline-start" />
        {t('helpers.pages.sched.add')}
      </Button>
      <AddDialog
        key={String(adding)}
        open={adding}
        flow={flow}
        graph={graph}
        specs={specs}
        onClose={() => setAdding(false)}
      />
    </SectionCard>
  )
}

function AddDialog({
  open,
  flow,
  graph,
  specs,
  onClose,
}: {
  open: boolean
  flow: FlowDetail
  graph: Graph
  specs: Specs
  onClose: () => void
}) {
  const { t, locale } = useI18n()
  const sentence = useSentence()
  const create = useCreateSchedule()
  const [cadence, setCadence] = useState<Schedule['cadence']>('daily')
  const [time, setTime] = useState('08:00')
  const [weekday, setWeekday] = useState(0)
  const [zone, setZone] = useState(detectZone)
  const [values, setValues] = useState<Record<string, string>>({})
  const [jobId, setJobId] = useState('')

  const input = graph.nodes.find((n) => n.type === 'input')
  const fields = input?.type === 'input' ? input.fields : []
  const needsJob = graph.nodes.some(
    (n) =>
      n.type === 'agent' &&
      (specs.get(n.agent_version_id)?.context_sources ?? []).some(
        (s) => s === 'job' || s === 'fit',
      ),
  )
  const missing =
    fields.some((f) => (f.required ?? true) && !(values[f.name] ?? '').trim()) ||
    (needsJob && !jobId) ||
    (cadence !== 'hourly' && !time)
  const when: When = {
    cadence,
    at_time: cadence === 'hourly' ? null : time,
    weekday: cadence === 'weekly' ? weekday : null,
    timezone: zone,
  }
  const zones = ZONES.includes(zone) ? ZONES : [zone, ...ZONES]

  return (
    <Modal open={open} label={t('helpers.pages.sched.add')} onClose={onClose}>
      <form
        className="max-h-[80dvh] space-y-4 overflow-y-auto p-1"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate(
            {
              flowId: flow.id,
              body: { ...when, inputs: values, job_id: jobId || null },
            },
            { onSuccess: onClose },
          )
        }}
      >
        <h2 className="text-lg font-semibold tracking-tight">{t('helpers.pages.sched.add')}</h2>
        <fieldset className="space-y-2">
          <legend className="mb-1.5 text-sm font-medium">{t('helpers.pages.sched.cadence')}</legend>
          <div className="grid gap-2">
            {CADENCES.map((c) => (
              <ChoiceCard
                key={c}
                type="radio"
                name="cadence"
                checked={cadence === c}
                onChange={() => setCadence(c)}
                title={t(`helpers.pages.sched.cadence_${c}`)}
              />
            ))}
          </div>
        </fieldset>
        {cadence !== 'hourly' && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="sched-time">{t('helpers.pages.sched.time')}</Label>
              <Input
                id="sched-time"
                type="time"
                required
                value={time}
                onChange={(e) => setTime(e.target.value)}
              />
            </div>
            {cadence === 'weekly' && (
              <div className="space-y-1.5">
                <Label htmlFor="sched-day">{t('helpers.pages.sched.weekday')}</Label>
                <NativeSelect
                  id="sched-day"
                  className="w-full"
                  value={weekday}
                  onChange={(e) => setWeekday(Number(e.target.value))}
                >
                  {Array.from({ length: 7 }, (_, d) => (
                    <option key={d} value={d}>
                      {dayName(d, locale)}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            )}
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="sched-zone">{t('helpers.pages.sched.zone')}</Label>
          <NativeSelect
            id="sched-zone"
            className="w-full"
            value={zone}
            onChange={(e) => setZone(e.target.value)}
          >
            {zones.map((z) => (
              <option key={z} value={z}>
                {city(z)} ({z})
              </option>
            ))}
          </NativeSelect>
          <p className="text-xs text-muted-foreground">
            {t('helpers.pages.sched.zone_hint', { zone: city(zone) })}
          </p>
        </div>
        {fields.map((f) => (
          <div key={f.name} className="space-y-1.5">
            <Label htmlFor={`sched-${f.name}`}>{f.label}</Label>
            <Textarea
              id={`sched-${f.name}`}
              rows={3}
              maxLength={MAX_INPUT_CHARS}
              value={values[f.name] ?? ''}
              onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
            />
          </div>
        ))}
        {needsJob && <JobSelect id="sched-job" value={jobId} onChange={setJobId} />}
        <p className="font-medium">{t('helpers.pages.sched.summary', { when: sentence(when) })}</p>
        <p className="flex items-start gap-2 rounded-xl border bg-muted/50 px-3 py-2.5 text-sm text-muted-foreground">
          <Sparkles aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>
            {t('helpers.pages.sched.cost', { count: aiCalls(graph), max: MAX_SCHEDULES })}
          </span>
        </p>
        <ErrorMessage error={create.error} />
        <div className="flex justify-end gap-2 border-t pt-4">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('helpers.cancel')}
          </Button>
          <Button type="submit" disabled={missing || create.isPending}>
            {create.isPending && <Spinner />}
            {t('helpers.pages.sched.save')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
