/** Route guards via GET /api/auth/me (D-037). */
import { Navigate, Outlet, useLocation } from 'react-router'
import { isApiError } from '../api/errors'
import { Card, PageSkeleton } from '../components/ui/Card'
import { ErrorState } from '../components/ui/ErrorState'
import { useMe } from '../features/auth/queries'

function loginTarget(pathname: string, search: string): string {
  return `/login?next=${encodeURIComponent(pathname + search)}`
}

export function RequireAgent() {
  const me = useMe()
  const location = useLocation()
  if (me.isPending) {
    return <div className="mx-auto max-w-6xl p-4"><PageSkeleton /></div>
  }
  if (me.isError) {
    if (isApiError(me.error) && me.error.status === 401) {
      return <Navigate to={loginTarget(location.pathname, location.search)} replace />
    }
    return (
      <div className="mx-auto max-w-xl p-4">
        <ErrorState error={me.error} onRetry={() => void me.refetch()} />
      </div>
    )
  }
  return <Outlet />
}

export function RequireLead() {
  const me = useMe()
  if (me.data?.role !== 'lead') {
    return (
      <Card className="mx-auto max-w-xl">
        <h1 className="text-xl font-semibold">You don't have access</h1>
        <p className="mt-2">This page is for the support lead.</p>
      </Card>
    )
  }
  return <Outlet />
}

/** `/` → the ticket list when signed in, otherwise the login page. */
export function RootRedirect() {
  const me = useMe()
  if (me.isPending) return <div className="mx-auto max-w-6xl p-4"><PageSkeleton /></div>
  return <Navigate to={me.isSuccess ? '/tickets' : '/login'} replace />
}
