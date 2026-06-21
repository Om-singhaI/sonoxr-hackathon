import type { ReactElement } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

// Gate the dashboard + patient viewer behind sign-in. The Login page sets
// localStorage.sonoxr_user on submit (front-end stub). No user → bounce to /login.
export default function RequireAuth({ children }: { children: ReactElement }) {
  const authed = typeof window !== 'undefined' && !!localStorage.getItem('sonoxr_user')
  const loc = useLocation()
  if (!authed) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  return children
}
