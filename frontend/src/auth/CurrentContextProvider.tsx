import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { getCurrentContext } from './auth.service'
import { CurrentContextStore, type CurrentContextState } from './current-context'
import { getSession, getSessionRevision, subscribeSession } from './session'
import { businessTimeRemaining } from './business-time'
import type { ResolvedCurrentContext } from './types'
import { ApiError } from '../lib/api'

export default function CurrentContextProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CurrentContextState>({ status: 'loading', data: null })
  const [errorMessage, setErrorMessage] = useState('')
  const refreshRef = useRef<() => Promise<ResolvedCurrentContext>>(async () => { throw new Error('Contexto no disponible.') })
  const organizationRef = useRef<string | null>(null)
  const revisionRef = useRef<number | null>(null)
  const refreshCurrentContext = useCallback(() => refreshRef.current(), [])
  const isCurrentOrganization = useCallback((id: string) => organizationRef.current === id && revisionRef.current === getSessionRevision(), [])

  useEffect(() => {
    let alive = true, generation = 0
    let lastData: ResolvedCurrentContext | null = null
    let pending: Promise<ResolvedCurrentContext> | null = null
    let controller: AbortController | null = null
    let timer: ReturnType<typeof setTimeout>

    function invalidateTime() {
      if (lastData) {
        lastData = { ...lastData, businessTimeLease: null }
        setState({ status: 'loaded', data: lastData })
      }
    }
    function schedule(ms: number) {
      clearTimeout(timer)
      timer = setTimeout(() => {
        invalidateTime()
        void load().catch(() => {})
      }, ms)
    }
    function load(): Promise<ResolvedCurrentContext> {
      if (pending) return pending
      const session = getSession(), revision = getSessionRevision(), order = generation
      if (!session || !alive) return Promise.reject(new Error('No hay una sesión activa.'))
      const c = new AbortController()
      controller = c
      const valid = () => alive && !c.signal.aborted && order === generation && revision === getSessionRevision()
      pending = (async () => {
        try {
          const data = await getCurrentContext(session.access, c.signal)
          if (!valid()) throw new Error('El contexto cambió durante la lectura.')
          lastData = data
          organizationRef.current = data.organization?.id ?? null
          revisionRef.current = revision
          setState({ status: 'loaded', data })
          if (data.organization) schedule(businessTimeRemaining(data.businessTimeLease) || 60000)
          else clearTimeout(timer)
          return data
        } catch (cause) {
          if (valid()) {
            invalidateTime()
            setErrorMessage(cause instanceof ApiError && cause.status === 403
              ? 'No tienes acceso al contexto actual de la organización.' : 'No fue posible cargar el contexto actual.')
            if (!lastData) setState({ status: 'error', data: null })
            schedule(60000)
          }
          throw cause
        } finally { if (order === generation) pending = null }
      })()
      return pending
    }
    function reset() {
      generation++
      controller?.abort()
      clearTimeout(timer)
      pending = null
      lastData = null
      organizationRef.current = null
      revisionRef.current = null
      setState({ status: 'loading', data: null })
      void load().catch(() => {})
    }
    function refreshOnFocus() {
      invalidateTime()
      void load().catch(() => {})
    }
    function onVisibility() { if (document.visibilityState === 'visible') refreshOnFocus() }
    refreshRef.current = load
    const unsubscribe = subscribeSession(reset)
    window.addEventListener('focus', refreshOnFocus)
    document.addEventListener('visibilitychange', onVisibility)
    void load().catch(() => {})
    return () => {
      alive = false
      generation++
      controller?.abort()
      clearTimeout(timer)
      unsubscribe()
      window.removeEventListener('focus', refreshOnFocus)
      document.removeEventListener('visibilitychange', onVisibility)
      organizationRef.current = null
      revisionRef.current = null
    }
  }, [])

  return <CurrentContextStore.Provider value={{ ...state, refreshCurrentContext, isCurrentOrganization }}>
    {state.status === 'loading' ? <p role="status">Cargando contexto...</p>
      : state.status === 'error' ? <div>
        <p role="alert">{errorMessage}</p>
        <button type="button" onClick={() => { void refreshCurrentContext().catch(() => {}) }}>Reintentar</button>
      </div> : children}
  </CurrentContextStore.Provider>
}
