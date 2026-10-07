import { zodResolver } from '@hookform/resolvers/zod'
import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'
import { z } from 'zod'
import { ErrorMessage } from '@/components/ErrorMessage'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { signInWithEmail, signInWithGoogle, signUpWithEmail } from '@/lib/auth'

const schema = z.object({
  email: z.string().email('Enter a valid email address.'),
  password: z.string().min(8, 'At least 8 characters.'),
})
type Values = z.infer<typeof schema>

const MESSAGES: Record<string, string> = {
  'auth/invalid-credential': 'Wrong email or password.',
  'auth/user-not-found': 'Wrong email or password.',
  'auth/wrong-password': 'Wrong email or password.',
  'auth/email-already-in-use': 'An account with this email already exists.',
  'auth/popup-closed-by-user': 'Sign-in cancelled.',
  'auth/popup-blocked': 'The sign-in popup was blocked. Allow popups for this site and retry.',
  'auth/network-request-failed': 'Network error. Check your connection and retry.',
}

// Never show raw SDK text: map the error code or fall back to a generic message.
const errorMessage = (e: unknown) =>
  MESSAGES[(e as { code?: string }).code ?? ''] ?? 'Sign-in failed. Please try again.'

export function SignIn() {
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [error, setError] = useState<string>()
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
      setError(errorMessage(e))
    }
  }

  const onSubmit = ({ email, password }: Values) =>
    run(() =>
      mode === 'signin' ? signInWithEmail(email, password) : signUpWithEmail(email, password),
    )

  return (
    <main className="grid min-h-screen md:grid-cols-2">
      <section className="hidden flex-col justify-between bg-linear-to-br from-indigo-600 to-violet-700 p-10 text-white md:flex">
        <p className="flex items-center gap-2 text-lg font-semibold">
          <Sparkles className="size-5" /> RecruitAI
        </p>
        <div className="space-y-3">
          <p className="text-3xl leading-tight font-semibold tracking-tight">
            Your job search, with a coach by your side.
          </p>
          <p className="max-w-md text-white/80">
            Build your profile from your CV, find the jobs that fit, and write letters that sound
            like you.
          </p>
        </div>
        <p className="text-sm text-white/70">Your data stays yours: export or delete it anytime.</p>
      </section>
      <section className="flex items-center justify-center p-6">
        <Card className="w-full max-w-sm shadow-none ring-0 md:bg-transparent">
          <CardHeader>
            <CardTitle className="text-xl">
              {mode === 'signin' ? 'Sign in' : 'Create your account'}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
              <div className="space-y-1">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" autoComplete="email" {...register('email')} />
                {errors.email && (
                  <p role="alert" className="text-sm text-destructive">
                    {errors.email.message}
                  </p>
                )}
              </div>
              <div className="space-y-1">
                <Label htmlFor="password">Password</Label>
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
              {error && <ErrorMessage error={{ detail: error }} />}
              <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
                {mode === 'signin' ? 'Sign in' : 'Sign up'}
              </Button>
            </form>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="h-px flex-1 bg-border" />
              or
              <span className="h-px flex-1 bg-border" />
            </div>
            <Button
              variant="outline"
              size="lg"
              className="w-full"
              onClick={() => run(signInWithGoogle)}
            >
              Continue with Google
            </Button>
            <Button
              variant="link"
              className="w-full"
              onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')}
            >
              {mode === 'signin' ? 'No account? Sign up' : 'Have an account? Sign in'}
            </Button>
            <p className="text-center text-xs text-muted-foreground">
              Your data stays in the EU and is never used to train AI.{' '}
              <Link to="/privacy" className="underline">
                Privacy policy
              </Link>
            </p>
          </CardContent>
        </Card>
      </section>
    </main>
  )
}
