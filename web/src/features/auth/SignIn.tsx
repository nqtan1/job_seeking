import { zodResolver } from '@hookform/resolvers/zod'
import { CircleAlert, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'
import { z } from 'zod'
import { LanguageSelect } from '@/components/LanguageSelect'
import { useT, type Key } from '@/i18n'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { clearEndReason, peekEndReason } from '@/lib/session'
import { signInWithEmail, signInWithGoogle, signUpWithEmail } from '@/lib/auth'

type Values = { email: string; password: string }

const MESSAGES: Record<string, Key> = {
  'auth/invalid-credential': 'auth.err.credentials',
  'auth/user-not-found': 'auth.err.credentials',
  'auth/wrong-password': 'auth.err.credentials',
  'auth/email-already-in-use': 'auth.err.exists',
  'auth/popup-closed-by-user': 'auth.err.cancelled',
  'auth/popup-blocked': 'auth.err.popup',
  'auth/network-request-failed': 'auth.err.network',
}

// Never show raw SDK text: map the error code or fall back to a generic message.
const errorKey = (e: unknown): Key =>
  MESSAGES[(e as { code?: string }).code ?? ''] ?? 'auth.err.generic'

const REASONS: Record<string, Key> = {
  idle: 'auth.reason.idle',
  reauth: 'auth.reason.reauth',
  'other-tab': 'auth.reason.other_tab',
}

export function SignIn() {
  const t = useT()
  const schema = z.object({
    email: z.string().email(t('auth.email_invalid')),
    password: z.string().min(8, t('auth.password_min')),
  })
  const [reason] = useState(() => REASONS[peekEndReason() ?? ''])
  useEffect(() => clearEndReason, [])
  const [remember, setRemember] = useState(false)
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [error, setError] = useState<Key>()
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) })

  const run = async (fn: () => Promise<unknown>) => {
    setError(undefined)
    try {
      await fn()
    } catch (e) {
      setError(errorKey(e))
    }
  }

  const onSubmit = ({ email, password }: Values) =>
    run(() =>
      mode === 'signin'
        ? signInWithEmail(email, password, remember)
        : signUpWithEmail(email, password, remember),
    )

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
            <CardTitle className="text-xl">
              {mode === 'signin' ? t('auth.sign_in') : t('auth.create_account')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
              <div className="space-y-1">
                <Label htmlFor="email">{t('auth.email')}</Label>
                <Input id="email" type="email" autoComplete="email" {...register('email')} />
                {errors.email && (
                  <p role="alert" className="text-sm text-destructive">
                    {errors.email.message}
                  </p>
                )}
              </div>
              <div className="space-y-1">
                <Label htmlFor="password">{t('auth.password')}</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                  {...register('password')}
                />
                {errors.password && (
                  <p role="alert" className="text-sm text-destructive">
                    {errors.password.message}
                  </p>
                )}
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                />
                {t('auth.remember')}
              </label>
              {reason && !error && (
                <p role="status" className="text-sm text-muted-foreground">
                  {t(reason)}
                </p>
              )}
              {error && (
                <p
                  role="alert"
                  className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
                >
                  <CircleAlert className="mt-0.5 size-4 shrink-0" />
                  {t(error)}
                </p>
              )}
              <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
                {mode === 'signin' ? t('auth.sign_in') : t('auth.sign_up')}
              </Button>
            </form>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="h-px flex-1 bg-border" />
              {t('auth.or')}
              <span className="h-px flex-1 bg-border" />
            </div>
            <Button
              variant="outline"
              size="lg"
              className="w-full"
              onClick={() => run(() => signInWithGoogle(remember))}
            >
              {t('auth.google')}
            </Button>
            <Button
              variant="link"
              className="w-full"
              onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')}
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
