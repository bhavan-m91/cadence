import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { Logo } from '../ui/Icon'

export function Splash() {
  return <div className="flex min-h-screen items-center justify-center" role="status" aria-label="Loading"><Logo size={44} /></div>
}

/** Redirect to /login without a session; to /onboarding until it is completed (PRD 8.2). */
export function RouteGuard() {
  const status = useAuthStore((s) => s.status)
  const user = useAuthStore((s) => s.user)
  const loc = useLocation()
  if (status === 'loading') return <Splash />
  if (status === 'anon' || !user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />
  if (!user.onboarding_completed && loc.pathname !== '/onboarding') return <Navigate to="/onboarding" replace />
  return <Outlet />
}

export function PublicOnly() {
  const status = useAuthStore((s) => s.status)
  const user = useAuthStore((s) => s.user)
  if (status === 'loading') return <Splash />
  if (status === 'authed' && user) return <Navigate to={user.onboarding_completed ? '/overview' : '/onboarding'} replace />
  return <Outlet />
}
