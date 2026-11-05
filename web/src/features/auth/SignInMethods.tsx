import { useReducer, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useT, type Key } from '@/i18n'
import {
  addPassword,
  authErrorKey,
  connectGoogle,
  resendVerification,
  sendPasswordReset,
  signInMethods,
} from '@/lib/auth'

const MIN_PASSWORD = 8

/** Settings card: the ways this account can sign in. A Google account can get a password (and
 *  the other way round) without becoming a second account. */
export function SignInMethods() {
  const t = useT()
  const [, refresh] = useReducer((n: number) => n + 1, 0)
  const m = signInMethods()
  const email = m.email
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Key>()
  const [done, setDone] = useState<Key>()
  const running = useRef(false)

  const run = async (fn: () => Promise<unknown>, ok: Key) => {
    if (running.current) return
    running.current = true
    setError(undefined)
    setDone(undefined)
    setBusy(true)
    try {
      await fn()
      setDone(ok)
    } catch (e) {
      setError(authErrorKey(e))
    } finally {
      running.current = false
      setBusy(false)
      refresh()
    }
  }

  const invalid =
    password.length < MIN_PASSWORD
      ? 'auth.password_min'
      : password !== confirm
        ? 'auth.password_match'
        : undefined

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('auth.methods.title')}</CardTitle>
        <CardDescription>{t('auth.methods.desc')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <span>
            Google{' '}
            <span className="text-sm text-muted-foreground">
              {m.google ? t('auth.methods.on') : t('auth.methods.off')}
            </span>
          </span>
          {!m.google && (
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => run(connectGoogle, 'auth.methods.google_added')}
            >
              {t('auth.methods.connect_google')}
            </Button>
          )}
        </div>

        <div className="space-y-2">
          <p>
            {t('auth.methods.password')}{' '}
            <span className="text-sm text-muted-foreground">
              {m.password ? t('auth.methods.on') : t('auth.methods.off')}
            </span>
          </p>
          {m.password ? (
            <div className="flex flex-wrap gap-2">
              {email && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => run(() => sendPasswordReset(email), 'auth.methods.reset_sent')}
                >
                  {t('auth.methods.change_password')}
                </Button>
              )}
              {!m.verified && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => run(resendVerification, 'auth.methods.verify_sent')}
                >
                  {t('auth.methods.resend_verification')}
                </Button>
              )}
            </div>
          ) : (
            <form
              className="space-y-2"
              noValidate
              onSubmit={(e) => {
                e.preventDefault()
                if (invalid) {
                  setDone(undefined)
                  return setError(invalid)
                }
                void run(async () => {
                  await addPassword(password)
                  setPassword('')
                  setConfirm('')
                }, 'auth.methods.password_added')
              }}
            >
              <p className="text-sm text-muted-foreground">{t('auth.methods.add_hint')}</p>
              <input type="email" autoComplete="username" value={email ?? ''} readOnly hidden />
              <Label htmlFor="new-password">{t('auth.methods.new_password')}</Label>
              <Input
                id="new-password"
                type="password"
                aria-invalid={!!error}
                aria-describedby="methods-status"
                autoComplete="new-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value)
                  setError(undefined)
                }}
              />
              <Label htmlFor="new-password-confirm">{t('auth.password_confirm')}</Label>
              <Input
                id="new-password-confirm"
                type="password"
                aria-invalid={!!error}
                aria-describedby="methods-status"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => {
                  setConfirm(e.target.value)
                  setError(undefined)
                }}
              />
              <Button type="submit" size="sm" disabled={busy}>
                {t('auth.methods.add_password')}
              </Button>
            </form>
          )}
        </div>

        <p role="status" className="text-sm text-muted-foreground empty:hidden">
          {done ? t(done) : ''}
        </p>
        <p id="methods-status" role="alert" className="text-sm text-destructive empty:hidden">
          {error ? t(error) : ''}
        </p>
      </CardContent>
    </Card>
  )
}
