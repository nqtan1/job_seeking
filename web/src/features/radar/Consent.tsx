import { useState } from 'react'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Modal } from '@/components/Modal'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useMe } from '@/features/settings/api'
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
  return (
    <div className="space-y-2 text-sm">
      <p>
        If you switch this on, RecruitAI runs your saved job searches once a day, even when you are
        not signed in.
      </p>
      <ul className="list-disc space-y-1 pl-5">
        <li>
          <strong>What runs:</strong> we query a public job-offer source (France Travail) with your
          search terms, then an AI model compares each new offer with your profile to give a fit
          score. The AI receives your profile summary and the offer text, nothing else.
        </li>
        <li>
          <strong>What we keep:</strong> the offers found, their scores, and a log of each run.
        </li>
        <li>
          <strong>What we email you:</strong> a short message with job title, company and a link. No
          CV content.
        </li>
        <li>
          <strong>Limits:</strong> at most 3 searches, once a day. Everything pauses automatically
          if you have not signed in for 60 days (we warn you at 53 days) or if a search keeps
          failing.
        </li>
        <li>
          <strong>Stopping:</strong> switch it off here or with the link in any email, at any time.
          Withdrawing pauses all searches immediately. We never apply to jobs on your behalf.
        </li>
      </ul>
    </div>
  )
}

function ConsentDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
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
    <Modal open={open} label="Background job radar" onClose={onClose}>
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Let RecruitAI search for jobs for you</h2>
        <ConsentText />
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
          />
          I agree that RecruitAI runs these searches in the background.
        </label>
        {denied && (
          <p role="alert" className="text-sm text-destructive">
            We could not confirm it is you. Nothing was changed.
          </p>
        )}
        {grant.isError && <ErrorMessage error={grant.error} />}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!agreed || grant.isPending || !consent.data} onClick={enable}>
            Enable background radars
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/** Top of the radar page: consent state, and a one-click resume after an automatic pause. */
export function ConsentBanner() {
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
          Background search
          <StatusBadge tone="warning">
            {state === 'granted' ? 'paused' : state === 'needs_reconsent' ? 'needs consent' : 'off'}
          </StatusBadge>
        </CardTitle>
        <CardDescription>
          {state === 'granted'
            ? 'Some radars were paused (no sign-in for a long time, or repeated failures).'
            : state === 'needs_reconsent'
              ? 'The consent text changed. Radars stay paused until you agree again.'
              : 'Your radars do not run automatically until you agree to background searches.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {state === 'granted' ? (
          <Button disabled={resume.isPending} onClick={() => resume.mutate()}>
            Resume radars
          </Button>
        ) : (
          <Button onClick={() => setOpen(true)}>Review and enable</Button>
        )}
        {resume.isError && <ErrorMessage error={resume.error} />}
        <ConsentDialog open={open} onClose={() => setOpen(false)} />
      </CardContent>
    </Card>
  )
}

/** Settings: current state, history, withdraw. */
export function ConsentSettings() {
  const consent = useConsent()
  const withdraw = useWithdrawConsent()
  const [open, setOpen] = useState(false)
  const c = consent.data
  return (
    <Card>
      <CardHeader>
        <CardTitle>Background job radar</CardTitle>
        <CardDescription>
          Searches that run without you being signed in need your consent. You can withdraw it at
          any time.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {consent.isError && <ErrorMessage error={consent.error} />}
        {c && (
          <>
            <p className="text-sm">
              Status: <strong>{c.state === 'needs_reconsent' ? 'needs new consent' : c.state}</strong>
            </p>
            {c.state === 'granted' ? (
              <Button
                variant="outline"
                disabled={withdraw.isPending}
                onClick={() => withdraw.mutate()}
              >
                Withdraw consent
              </Button>
            ) : (
              <Button onClick={() => setOpen(true)}>Review and enable</Button>
            )}
            {c.history.length > 0 && (
              <ul className="space-y-1 text-sm text-muted-foreground" aria-label="Consent history">
                {c.history.map((h) => (
                  <li key={h.at + h.event}>
                    {h.event === 'granted' ? 'Granted' : 'Withdrawn'} on{' '}
                    {new Date(h.at).toLocaleDateString()} ({h.source === 'ui' ? 'in the app' : 'email link'})
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
