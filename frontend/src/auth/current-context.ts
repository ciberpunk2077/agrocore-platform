import { createContext, useContext } from 'react'
import type { ResolvedCurrentContext } from './types'
import { businessTimeIsFresh } from './business-time'

export type CurrentContextState =
  | { status: 'loading'; data: null }
  | { status: 'error'; data: null }
  | { status: 'loaded'; data: ResolvedCurrentContext }

export interface CurrentContextControls {
  refreshCurrentContext: () => Promise<ResolvedCurrentContext>
  isCurrentOrganization: (organizationId: string) => boolean
}

export const CurrentContextStore = createContext<(CurrentContextState & CurrentContextControls) | null>(null)

export function useCurrentContext() {
  const state = useContext(CurrentContextStore)
  if (!state) throw new Error('Current context requires CurrentContextProvider')
  return {
    ...state,
    currentUser: state.data?.current_user ?? null,
    currentOrganization: state.data?.organization ?? null,
    currentMembership: state.data?.membership ?? null,
    currentRole: state.data?.role ?? null,
    canRead: state.data?.can_read ?? false,
    canWrite: (typeof __AGROCORE_DEMO__ !== 'undefined' && __AGROCORE_DEMO__) ? false : state.data?.can_write ?? false,
    businessTimeLease: state.data?.businessTimeLease ?? null,
    businessTimeReady: businessTimeIsFresh(state.data?.businessTimeLease ?? null),
  }
}
