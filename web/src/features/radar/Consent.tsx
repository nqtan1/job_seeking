import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Modal } from '@/components/Modal'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useMe } from '@/features/settings/api'
import { useI18n, useT } from '@/i18n'
import { ensureRecentAuth } from '@/lib/stepup'
import {
  useConsent,
  useGrantConsent,
  useResumeRadars,
  useSearches,
  useWithdrawConsent,
} from './api'

/** DRAFT wording: owner/legal review required before release (ADR 0024). */
export function ConsentText() {
  const t = useT()
  const items = [
    ['radar.c.runs_h', 'radar.c.runs'],
    ['radar.c.keep_h', 'radar.c.keep'],
    ['radar.c.email_h', 'radar.c.email'],
    ['radar.c.limits_h', 'radar.c.limits'],
    ['radar.c.stop_h', 'radar.c.stop'],
  ] as const
  return (
    <div className="space-y-2 text-sm">
      <p>{t('radar.c.text_intro')}</p>
      <ul className="list-disc space-y-1 pl-5">
        {items.map(([h, b]) => (
          <li key={h}>
            <strong>{t(h)}</strong> {t(b)}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ConsentDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT()
  const consent = useConsent()
  const me = useMe()
  const grant = useGrantConsent()
  const [agreed, setAgreed] = useState(false)
  const [denied, setDenied] = useState(false)
  const maxAge = me.data?.session.stepup_max_age_seconds ?? 300

  const enable = async () => {
    setDenied(false)
    if (!consent.data) return
    if (!(await ensureRecentAuth(maxAge))) return setDenied(true)
    grant.mutate(consent.data.policy_version, {
      onSuccess: () => {
        setAgreed(false)
        onClose()
      },
    })
  }
  return (
    <Modal open={open} label={t('radar.c.dialog_label')} onClose={onClose}>
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">{t('radar.c.dialog_title')}</h2>
        <ConsentText />
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
          />
          {t('radar.c.agree')}
        </label>
        {denied && (
          <p role="alert" className="text-sm text-destructive">
            {t('radar.c.denied')}
          </p>
        )}
        {grant.isError && <ErrorMessage error={grant.error} />}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t('radar.c.cancel')}
          </Button>
          <Button disabled={!agreed || grant.isPending || !consent.data} onClick={enable}>
            {t('radar.c.enable')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/** Top of the radar page: consent state, and a one-click resume after an automatic pause. */
export function ConsentBanner() {
  const t = useT()
  const consent = useConsent()
  const searches = useSearches()
  const resume = useResumeRadars()
  const [open, setOpen] = useState(false)
  const state = consent.data?.state
  if (!state) return null
  const held = searches.data?.some(
    (s) => s.paused_reason === 'inactive' || s.paused_reason === 'failures',
  )
  if (state === 'granted' && !held) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {t('radar.c.banner_title')}
          <StatusBadge tone="warning">
            {state === 'granted'
              ? t('radar.c.badge_paused')
              : state === 'needs_reconsent'
                ? t('radar.c.badge_needs')
                : t('radar.c.badge_off')}
          </StatusBadge>
        </CardTitle>
        <CardDescription>
          {state === 'granted'
            ? t('radar.c.desc_granted')
            : state === 'needs_reconsent'
              ? t('radar.c.desc_needs')
              : t('radar.c.desc_off')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {state === 'granted' ? (
          <Button disabled={resume.isPending} onClick={() => resume.mutate()}>
            {t('radar.c.resume')}
          </Button>
        ) : (
          <Button onClick={() => setOpen(true)}>{t('radar.c.review')}</Button>
        )}
        {resume.isError && <ErrorMessage error={resume.error} />}
        <ConsentDialog open={open} onClose={() => setOpen(false)} />
      </CardContent>
    </Card>
  )
}

/** Settings: current state, history, withdraw. */
export function ConsentSettings() {
  const { t, locale } = useI18n()
  const consent = useConsent()
  const withdraw = useWithdrawConsent()
  const [open, setOpen] = useState(false)
  const c = consent.data
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('radar.c.set_title')}</CardTitle>
        <CardDescription>{t('radar.c.set_desc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {consent.isError && <ErrorMessage error={consent.error} />}
        {c && (
          <>
            <p className="text-sm">
              {t('radar.c.status')} <strong>{t(`radar.c.state_${c.state}`)}</strong>
            </p>
            {c.state === 'granted' ? (
              <Button
                variant="outline"
                disabled={withdraw.isPending}
                onClick={() => withdraw.mutate()}
              >
                {t('radar.c.withdraw')}
              </Button>
            ) : (
              <Button onClick={() => setOpen(true)}>{t('radar.c.review')}</Button>
            )}
            {c.history.length > 0 && (
              <ul
                className="space-y-1 text-sm text-muted-foreground"
                aria-label={t('radar.c.history')}
              >
                {c.history.map((h) => (
                  <li key={h.at + h.event}>
                    {t(h.event === 'granted' ? 'radar.c.hist_granted' : 'radar.c.hist_withdrawn', {
                      date: new Date(h.at).toLocaleDateString(locale),
                      source: t(h.source === 'ui' ? 'radar.c.src_ui' : 'radar.c.src_email'),
                    })}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        <ConsentDialog open={open} onClose={() => setOpen(false)} />
      </CardContent>
    </Card>
  )
}
