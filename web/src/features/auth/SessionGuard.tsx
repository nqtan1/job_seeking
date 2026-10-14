import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Modal } from '@/components/Modal'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useMe } from '@/features/settings/api'
import { isRemembered, reauthenticate, signOut, usesPassword } from '@/lib/auth'
import {
  broadcastSignOut,
  registerEndSession,
  setEndReason,
  useIdleSession,
  useSignOutBroadcast,
  type EndReason,
} from '@/lib/session'
import { registerReauthDialog } from '@/lib/stepup'

function ReauthDialog() {
  const [done, setDone] = useState<((ok: boolean) => void) | null>(null)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    registerReauthDialog((cb) => {
      setPassword('')
      setError(undefined)
      setDone(() => cb)
    })
    return () => registerReauthDialog(undefined)
  }, [])

  const finish = (ok: boolean) => {
    done?.(ok)
    setDone(null)
  }
  const confirm = async () => {
    setBusy(true)
    setError(undefined)
    try {
      await reauthenticate(password)
      finish(true)
    } catch {
      setError('That did not work. Check your password and try again.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={done !== null} label="Confirm it is you" onClose={() => finish(false)}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          void confirm()
        }}
      >
        <h2 className="text-lg font-semibold">Confirm it is you</h2>
        <p className="text-sm text-muted-foreground">
          This action is sensitive. Please confirm your identity to continue.
        </p>
        {usesPassword() && (
          <div className="space-y-1">
            <Label htmlFor="reauth-password">Password</Label>
            <Input
              id="reauth-password"
              type="password"
              autoComplete="current-password"
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => finish(false)}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy || (usesPassword() && !password)}>
            {usesPassword() ? 'Confirm' : 'Continue with Google'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/** Mounted once inside the signed-in app: idle timer + warning, tab sync, step-up dialog. */
export function SessionGuard() {
  const me = useMe()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const policy = me.data?.session
  const limit = policy ? (isRemembered() ? policy.idle_minutes_remembered : policy.idle_minutes) : 0

  // Kept in a ref: the registrations below must not be torn down on every navigation.
  const leaveRef = useRef<(reason: EndReason) => Promise<void>>(async () => {})
  useEffect(() => {
    leaveRef.current = async (reason) => {
      setEndReason(reason)
      qc.clear() // nothing of this account stays in memory
      if (reason !== 'other-tab') broadcastSignOut()
      await signOut().catch(() => {})
      navigate('/signin', { replace: true })
    }
  })
  useEffect(() => {
    registerEndSession((reason) => void leaveRef.current(reason))
    return () => registerEndSession(undefined)
  }, [])
  useSignOutBroadcast(() => void leaveRef.current('other-tab'))

  const idle = useIdleSession(limit, limit > 0)
  const minutes = Math.floor(idle.secondsLeft / 60)
  const seconds = String(idle.secondsLeft % 60).padStart(2, '0')
  return (
    <>
      <Modal open={idle.state === 'warning'} label="Stay signed in?">
        <div className="space-y-4" role="alertdialog" aria-describedby="idle-text">
          <h2 className="text-lg font-semibold">Stay signed in?</h2>
          <p id="idle-text" className="text-sm text-muted-foreground">
            For your security you will be signed out in{' '}
            <span aria-live="polite">
              {minutes}:{seconds}
            </span>{' '}
            because of inactivity. Anything you have not saved will be lost.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => void leaveRef.current('idle')}>
              Sign out now
            </Button>
            <Button autoFocus onClick={idle.touch}>
              Stay signed in
            </Button>
          </div>
        </div>
      </Modal>
      <ReauthDialog />
    </>
  )
}
