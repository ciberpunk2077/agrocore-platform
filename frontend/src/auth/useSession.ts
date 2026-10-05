import { useSyncExternalStore } from 'react'

import { getSession, getSessionRevision, subscribeSession } from './session'

export function useSession() {
  const revision = useSyncExternalStore(subscribeSession, getSessionRevision)
  return { session: getSession(), revision }
}
