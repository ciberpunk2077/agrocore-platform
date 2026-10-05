import type { ReactNode } from 'react'

import { useCurrentContext } from './current-context'

function WriteOnly({ children, fallback = null }: { children: ReactNode; fallback?: ReactNode }) {
  const { canWrite } = useCurrentContext()
  return canWrite ? children : fallback
}

export default WriteOnly
