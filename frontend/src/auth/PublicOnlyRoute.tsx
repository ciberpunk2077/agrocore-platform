import { Navigate, Outlet } from 'react-router-dom'

import { useSession } from './useSession'

function PublicOnlyRoute() {
  const { session } = useSession()
  return session ? <Navigate to="/dashboard" replace /> : <Outlet />
}

export default PublicOnlyRoute
