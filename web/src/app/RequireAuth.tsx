import { Navigate, Outlet, useLocation } from 'react-router'
import { useT } from '@/i18n'
import { useAuthUser } from '@/lib/auth'

export function RequireAuth() {
  const t = useT()
  const user = useAuthUser()
  const location = useLocation()
  if (user === undefined) return <p className="p-8 text-muted-foreground">{t('app.loading')}</p>
  if (user === null) return <Navigate to="/signin" replace state={{ from: location }} />
  return <Outlet />
}
