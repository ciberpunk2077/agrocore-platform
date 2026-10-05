import { createContext, useContext } from 'react'
import type { CurrentContext } from './types'

export type CurrentContextState =
  | { status: 'loading'; data: null }
  | { status: 'error'; data: null }
  | { status: 'loaded'; data: CurrentContext }

export const CurrentContextStore = createContext<CurrentContextState | null>(null)

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
    canWrite: state.data?.can_write ?? false,
  }
}
