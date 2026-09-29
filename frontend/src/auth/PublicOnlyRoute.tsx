import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'

import { getCurrentUser } from './auth.service'
import { clearSession, getSession } from './session'

type AuthStatus = 'checking' | 'authenticated' | 'unauthenticated'

function PublicOnlyRoute() {
  const [status, setStatus] = useState<AuthStatus>('checking')

  useEffect(() => {
    let isActive = true

    async function verifySession() {
      const session = getSession()

      if (!session) {
        if (isActive) {
          setStatus('unauthenticated')
        }

        return
      }

      try {
        await getCurrentUser(session.access)

        if (isActive) {
          setStatus('authenticated')
        }
      } catch {
        clearSession()

        if (isActive) {
          setStatus('unauthenticated')
        }
      }
    }

    void verifySession()

    return () => {
      isActive = false
    }
  }, [])

  if (status === 'checking') {
    return <p>Verificando sesión...</p>
  }

  if (status === 'authenticated') {
    return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}

export default PublicOnlyRoute