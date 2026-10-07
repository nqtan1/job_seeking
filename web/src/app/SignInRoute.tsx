import { Navigate, useLocation } from 'react-router'
import { SignIn } from '@/features/auth/SignIn'
import { useAuthUser } from '@/lib/auth'

export function SignInRoute() {
  const user = useAuthUser()
  const from = (useLocation().state as { from?: { pathname: string } } | null)?.from?.pathname
  return user ? <Navigate to={from ?? '/'} replace /> : <SignIn />
}
