import { Navigate, Outlet, useLocation } from 'react-router'
import { useAuthUser } from '@/lib/auth'

export function RequireAuth() {
  const user = useAuthUser()
  const location = useLocation()
  if (user === undefined) return <p className="p-8 text-muted-foreground">Loading…</p>
  if (user === null) return <Navigate to="/signin" replace state={{ from: location }} />
  return <Outlet />
}
