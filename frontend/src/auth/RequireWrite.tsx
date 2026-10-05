import type { ReactNode } from 'react'
import { generatePath, Navigate, useParams } from 'react-router-dom'

import { useCurrentContext } from './current-context'

function RequireWrite({ children, redirectTo }: { children: ReactNode; redirectTo: string }) {
  const { canWrite } = useCurrentContext()
  const params = useParams()
  return canWrite ? children : <Navigate to={generatePath(redirectTo, params)} replace />
}

export default RequireWrite
