import { useEffect, useState, type ReactNode } from 'react'
import { getCurrentContext } from './auth.service'
import { CurrentContextStore, type CurrentContextState } from './current-context'
import { getSession } from './session'
import { ApiError } from '../lib/api'

export default function CurrentContextProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CurrentContextState>({ status: 'loading', data: null })
  const [attempt, setAttempt] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      try {
        const session = getSession()
        if (!session) throw new Error('No active session')
        const data = await getCurrentContext(session.access, controller.signal)
        if (!controller.signal.aborted) setState({ status: 'loaded', data })
      } catch (cause) {
        if (!controller.signal.aborted) {
          setErrorMessage(cause instanceof ApiError && cause.status === 403
            ? 'No tienes acceso al contexto actual de la organización.'
            : 'No fue posible cargar el contexto actual.')
          setState({ status: 'error', data: null })
        }
      }
    }
    void load()
    return () => controller.abort()
  }, [attempt])

  return <CurrentContextStore.Provider value={state}>
    {state.status === 'loading' ? <p role="status">Cargando contexto...</p>
      : state.status === 'error' ? <div>
        <p role="alert">{errorMessage}</p>
        <button type="button" onClick={() => {
          setState({ status: 'loading', data: null })
          setAttempt((value) => value + 1)
        }}>Reintentar</button>
      </div> : children}
  </CurrentContextStore.Provider>
}
