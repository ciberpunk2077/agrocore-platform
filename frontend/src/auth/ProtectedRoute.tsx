import { Navigate, Outlet } from 'react-router-dom'

import { useSession } from './useSession'

function ProtectedRoute() {
  const { session, revision } = useSession()
  // CurrentContextProvider validates remotely before rendering business UI.
  return session ? <Outlet key={revision} /> : <Navigate to="/login" replace />
}

export default ProtectedRoute
