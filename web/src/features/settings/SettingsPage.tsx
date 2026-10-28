import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Page } from '@/components/Page'
import { Skeleton } from '@/components/Skeleton'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LanguageSelect } from '@/components/LanguageSelect'
import { useI18n, useT } from '@/i18n'
import { useTask } from '@/lib/api/tasks'
import { signOut } from '@/lib/auth'
import { ConsentSettings } from '@/features/radar/Consent'
import { ensureRecentAuth } from '@/lib/stepup'
import {
  useAiCalls,
  useDeleteAccount,
  useMe,
  useRevokeSessions,
  useSetReminders,
  useSetWeeklyGoal,
  useSetLanguage,
  useStartExport,
} from './api'

/** Runs `action` after a recent sign-in (asks again only when the last one is too old). */
function useStepUp() {
  const me = useMe()
  const [denied, setDenied] = useState(false)
  const guard = async (action: () => void) => {
    setDenied(false)
    if (await ensureRecentAuth(me.data?.session.stepup_max_age_seconds ?? 300)) action()
    else setDenied(true)
  }
  return { guard, denied }
}

function Denied() {
  const t = useT()
  return (
    <p role="alert" className="text-sm text-destructive">
      {t('settings.denied')}
    </p>
  )
}

const CONFIRM_WORD = 'DELETE'

function RemindersCard() {
  const t = useT()
  const me = useMe()
  const set = useSetReminders()
  const goal = useSetWeeklyGoal()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.rem.title')}</CardTitle>
        <CardDescription>{t('settings.rem.desc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={me.data?.email_reminders ?? true}
            disabled={me.isPending || set.isPending}
            onChange={(e) => set.mutate(e.target.checked)}
          />
          {t('settings.rem.send')}
        </label>
        {set.isError && <ErrorMessage error={set.error} />}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={me.data?.weekly_goal != null}
            disabled={me.isPending || goal.isPending}
            onChange={(e) => goal.mutate(e.target.checked ? 3 : null)}
          />
          {t('settings.rem.goal')}
        </label>
        {goal.isError && <ErrorMessage error={goal.error} />}
      </CardContent>
    </Card>
  )
}

function AiActivityCard() {
  const { t, locale } = useI18n()
  const calls = useAiCalls()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.ai.title')}</CardTitle>
        <CardDescription>{t('settings.ai.desc')}</CardDescription>
      </CardHeader>
      <CardContent>
        {calls.isError && <ErrorMessage error={calls.error} />}
        {calls.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('settings.ai.none')}</p>
        )}
        <ul className="space-y-1 text-sm">
          {calls.data?.slice(0, 10).map((c, i) => (
            <li key={i} className="flex flex-wrap justify-between gap-2">
              <span>
                {c.feature.split('@')[0].replace('_', ' ')}
                {c.status === 'error' && t('settings.ai.failed')}
              </span>
              <span className="text-muted-foreground tabular-nums">
                {t('settings.ai.row', {
                  when: new Date(c.at).toLocaleString(locale),
                  tokens: c.input_tokens + c.output_tokens,
                })}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

function ExportCard() {
  const t = useT()
  const start = useStartExport()
  const step = useStepUp()
  const task = useTask(start.data?.task_id)
  const running = start.isPending || task.data?.status === 'queued'
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.export.title')}</CardTitle>
        <CardDescription>{t('settings.export.desc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button disabled={running} onClick={() => step.guard(() => start.mutate())}>
          {running ? t('settings.export.preparing') : t('settings.export.request')}
        </Button>
        {step.denied && <Denied />}
        {start.isError && <ErrorMessage error={start.error} />}
        {task.isError && <ErrorMessage error={task.error} />}
        {task.data?.status === 'failed' && (
          <p role="alert" className="text-sm text-destructive">
            {t('settings.export.failed')}
          </p>
        )}
        {task.data?.status === 'done' && task.data.download_url && (
          <a href={task.data.download_url} download className="text-primary underline">
            {t('settings.export.download')}
          </a>
        )}
      </CardContent>
    </Card>
  )
}

function SessionsCard() {
  const t = useT()
  const revoke = useRevokeSessions()
  const step = useStepUp()
  const qc = useQueryClient()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.sessions.title')}</CardTitle>
        <CardDescription>{t('settings.sessions.desc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {step.denied && <Denied />}
        {revoke.isError && <ErrorMessage error={revoke.error} />}
        <Button
          variant="outline"
          disabled={revoke.isPending}
          onClick={() =>
            step.guard(() =>
              revoke.mutate(undefined, {
                onSuccess: async () => {
                  qc.clear()
                  await signOut().catch(() => {})
                },
              }),
            )
          }
        >
          {t('settings.sessions.button')}
        </Button>
      </CardContent>
    </Card>
  )
}

function DeleteCard() {
  const t = useT()
  const del = useDeleteAccount()
  const step = useStepUp()
  const qc = useQueryClient()
  const [typed, setTyped] = useState('')
  return (
    <Card className="border-destructive/50">
      <CardHeader>
        <CardTitle>{t('settings.delete.title')}</CardTitle>
        <CardDescription>{t('settings.delete.desc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Label htmlFor="confirm">{t('settings.delete.confirm', { word: CONFIRM_WORD })}</Label>
        <Input
          id="confirm"
          value={typed}
          autoComplete="off"
          onChange={(e) => setTyped(e.target.value)}
        />
        {step.denied && <Denied />}
        {del.isError && <ErrorMessage error={del.error} />}
        <Button
          variant="destructive"
          disabled={typed !== CONFIRM_WORD || del.isPending}
          onClick={() =>
            step.guard(() =>
              del.mutate(undefined, {
                onSuccess: async () => {
                  qc.clear() // no cached data of the deleted account stays in memory
                  await signOut().catch(() => {}) // the Firebase user is already gone server-side
                },
              }),
            )
          }
        >
          {del.isPending ? t('settings.delete.deleting') : t('settings.delete.button')}
        </Button>
      </CardContent>
    </Card>
  )
}

export function SettingsPage() {
  const t = useT()
  const setLanguage = useSetLanguage()
  const me = useMe()
  return (
    <Page title={t('settings.title')} description={t('settings.description')}>
      <div className="max-w-2xl space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>{t('lang.label')}</CardTitle>
            <CardDescription>{t('lang.hint')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <LanguageSelect onChange={(l) => setLanguage.mutate(l)} />
            {setLanguage.isError && <ErrorMessage error={setLanguage.error} />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('settings.account')}</CardTitle>
          </CardHeader>
          <CardContent>
            {me.isPending && <Skeleton className="h-5 w-48" />}
            {me.isError && <ErrorMessage error={me.error} />}
            {me.data && <p>{t('settings.signed_in_as', { email: me.data.user.email })}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {t('settings.plan')} <StatusBadge tone="info">{t('settings.free')}</StatusBadge>
            </CardTitle>
            <CardDescription>{t('settings.plan_hint')}</CardDescription>
          </CardHeader>
        </Card>
        <RemindersCard />
        <AiActivityCard />
        <ConsentSettings />
        <SessionsCard />
        <ExportCard />
        <DeleteCard />
      </div>
    </Page>
  )
}
