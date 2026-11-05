import { zodResolver } from '@hookform/resolvers/zod'
import { CircleAlert, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState, type ComponentProps } from 'react'
import { useForm, type FieldError } from 'react-hook-form'
import { Link } from 'react-router'
import { z } from 'zod'
import { LanguageSelect } from '@/components/LanguageSelect'
import { useT, type Key } from '@/i18n'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { clearEndReason, peekEndReason } from '@/lib/session'
import {
  authErrorKey,
  sendPasswordReset,
  signInWithEmail,
  signInWithGoogle,
  signUpWithEmail,
} from '@/lib/auth'

type Mode = 'signin' | 'signup' | 'reset'
type Values = { email: string; password: string; confirm: string }

const MIN_PASSWORD = 8 // new passwords only: older accounts may have a shorter one (the SDK allows 6)

const REASONS: Record<string, Key> = {
  idle: 'auth.reason.idle',
  reauth: 'auth.reason.reauth',
  'other-tab': 'auth.reason.other_tab',
}

const TITLES: Record<Mode, Key> = {
  signin: 'auth.sign_in',
  signup: 'auth.create_account',
  reset: 'auth.reset_title',
}
const SUBMITS: Record<Mode, Key> = {
  signin: 'auth.sign_in',
  signup: 'auth.sign_up',
  reset: 'auth.reset_send',
}

function Field({
  id,
  label,
  error,
  ...input
}: { id: string; label: string; error?: FieldError } & ComponentProps<typeof Input>) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : undefined}
        {...input}
      />
      <p id={`${id}-error`} role="alert" className="text-sm text-destructive empty:hidden">
        {error?.message}
      </p>
    </div>
  )
}

export function SignIn() {
  const t = useT()
  const [reason] = useState(() => REASONS[peekEndReason() ?? ''])
  useEffect(() => clearEndReason, [])
  const [remember, setRemember] = useState(false)
  const [mode, setMode] = useState<Mode>('signin')
  const [error, setError] = useState<Key>()
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false) // one request at a time: the form, Google, a reset
  const running = useRef(false) // set at once; `busy` only after the next render (Enter twice)

  const schema = z
    .object({
      email: z.string().trim().toLowerCase().email(t('auth.email_invalid')),
      password: z.string(),
      confirm: z.string(),
    })
    .superRefine((v, ctx) => {
      const issue = (path: keyof Values, message: Key) =>
        ctx.addIssue({ code: 'custom', path: [path], message: t(message) })
      if (mode === 'reset') return
      if (!v.password) issue('password', 'auth.password_required')
      else if (mode === 'signup' && v.password.length < MIN_PASSWORD)
        issue('password', 'auth.password_min')
      else if (mode === 'signup' && v.password !== v.confirm)
        issue('confirm', 'auth.password_match')
    })
  const {
    register,
    handleSubmit,
    resetField,
    setFocus,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '', confirm: '' }, // fields not on screen stay empty, not missing
  })

  const go = (next: Mode) => {
    setMode(next)
    setError(undefined)
    setSent(false)
    resetField('password')
    resetField('confirm')
    setTimeout(() => setFocus('email'), 0) // the clicked button just changed meaning
  }

  const run = async (fn: () => Promise<unknown>) => {
    if (running.current) return
    running.current = true
    setError(undefined)
    setBusy(true)
    try {
      await fn()
    } catch (e) {
      setError(authErrorKey(e))
    } finally {
      running.current = false
      setBusy(false)
    }
  }

  const onSubmit = ({ email, password }: Values) =>
    run(async () => {
      if (mode === 'reset') {
        try {
          await sendPasswordReset(email)
        } catch (e) {
          // Production answers the same for every address; the emulator says "no such account".
          if ((e as { code?: string }).code !== 'auth/user-not-found') throw e
        }
        setSent(true)
      } else if (mode === 'signin') await signInWithEmail(email, password, remember)
      else await signUpWithEmail(email, password, remember)
    })

  return (
    <main className="grid min-h-screen md:grid-cols-2">
      <section className="hidden flex-col justify-between bg-linear-to-br from-indigo-600 to-violet-700 p-10 text-white md:flex">
        <p className="flex items-center gap-2 text-lg font-semibold">
          <Sparkles className="size-5" /> RecruitAI
        </p>
        <div className="space-y-3">
          <p className="text-3xl leading-tight font-semibold tracking-tight">{t('auth.tagline')}</p>
          <p className="max-w-md text-white/80">{t('auth.pitch')}</p>
        </div>
        <p className="text-sm text-white/70">{t('auth.data_yours')}</p>
      </section>
      <section className="relative flex items-center justify-center p-6">
        <div className="absolute top-4 right-4 w-36">
          <LanguageSelect />
        </div>
        <Card className="w-full max-w-sm shadow-none ring-0 md:bg-transparent">
          <CardHeader>
            <CardTitle role="heading" aria-level={1} className="text-xl">
              {t(TITLES[mode])}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} className="space-y-4" noValidate>
              <Field
                id="email"
                label={t('auth.email')}
                type="email"
                autoComplete={mode === 'reset' ? 'email' : 'username'}
                error={errors.email}
                {...register('email')}
              />
              {mode !== 'reset' && (
                <Field
                  id="password"
                  label={t('auth.password')}
                  type="password"
                  autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                  error={errors.password}
                  {...register('password')}
                />
              )}
              {mode === 'signup' && (
                <Field
                  id="confirm"
                  label={t('auth.password_confirm')}
                  type="password"
                  autoComplete="new-password"
                  error={errors.confirm}
                  {...register('confirm')}
                />
              )}
              {mode === 'signin' && (
                <Button type="button" variant="link" className="px-0" onClick={() => go('reset')}>
                  {t('auth.forgot')}
                </Button>
              )}
              {mode !== 'reset' && (
                <label className="flex min-h-6 items-center gap-2 py-1 text-sm">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(e) => setRemember(e.target.checked)}
                  />
                  {t('auth.remember')}
                </label>
              )}
              {reason && !error && (
                <p role="status" className="text-sm text-muted-foreground">
                  {t(reason)}
                </p>
              )}
              <p role="status" className="text-sm text-muted-foreground empty:hidden">
                {sent ? t('auth.reset_sent') : ''}
              </p>
              <div role="alert" className="empty:hidden">
                {error && (
                  <div className="space-y-1 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    <p className="flex items-start gap-2">
                      <CircleAlert className="mt-0.5 size-4 shrink-0" />
                      {t(error)}
                    </p>
                    {/* Google-only accounts answer "wrong password" too: point to the way in. */}
                    {mode === 'signin' && error === 'auth.err.credentials' && (
                      <p>{t('auth.hint_google')}</p>
                    )}
                  </div>
                )}
              </div>
              <Button type="submit" size="lg" className="w-full" disabled={busy}>
                {t(SUBMITS[mode])}
              </Button>
            </form>
            {mode !== 'reset' && (
              <>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="h-px flex-1 bg-border" />
                  {t('auth.or')}
                  <span className="h-px flex-1 bg-border" />
                </div>
                <Button
                  variant="outline"
                  size="lg"
                  className="w-full"
                  disabled={busy}
                  onClick={() => run(() => signInWithGoogle(remember))}
                >
                  {t('auth.google')}
                </Button>
              </>
            )}
            <Button
              variant="link"
              className="w-full"
              onClick={() => go(mode === 'signin' ? 'signup' : 'signin')}
            >
              {mode === 'signin' ? t('auth.no_account') : t('auth.have_account')}
            </Button>
            <p className="text-center text-xs text-muted-foreground">
              {t('auth.eu_note')}{' '}
              <Link to="/privacy" className="underline">
                {t('auth.privacy_link')}
              </Link>
            </p>
          </CardContent>
        </Card>
      </section>
    </main>
  )
}
