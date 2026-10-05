import { useEffect, useState } from 'react'
import { getSession, getSessionRevision } from '../../auth/session'
import { ApiError } from '../../lib/api'
import { normalizeApiError } from '../../lib/api-errors'
import { getWeight } from '../weights.service'
import type { Weight } from '../types'
import type { WeighingMethod } from '../types'
import WeightEditForm from './WeightEditForm'

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string; retry: boolean }
  | { status: 'ready'; record: Weight }

function WeightPreparation({ weightId, animalId, methods, birthDate, catalogError, onCancel, onSaved, onRecheck }: {
  weightId: string
  animalId: string
  methods: WeighingMethod[]
  birthDate: string | null
  catalogError: string | null
  onCancel: () => void
  onSaved: () => void
  onRecheck: () => void
}) {
  const [attempt, setAttempt] = useState(0)
  return <section aria-label="Edición de pesaje">
    <h3>Editar pesaje existente</h3>
    <LoadedWeight key={attempt} weightId={weightId} animalId={animalId}
      methods={methods} birthDate={birthDate} catalogError={catalogError} onCancel={onCancel} onSaved={onSaved} onRecheck={onRecheck}
      onRetry={() => setAttempt((value) => value + 1)} />
  </section>
}

function LoadedWeight({ weightId, animalId, methods, birthDate, catalogError, onRetry, onCancel, onSaved, onRecheck }: {
  weightId: string; animalId: string; methods: WeighingMethod[]; birthDate: string | null
  catalogError: string | null; onRetry: () => void; onCancel: () => void; onSaved: () => void; onRecheck: () => void
}) {
  const [state, setState] = useState<State>({ status: 'loading' })
  useEffect(() => {
    const controller = new AbortController()
    const revision = getSessionRevision()
    async function load() {
      const session = getSession()
      if (!session) {
        setState({ status: 'error', message: 'No hay una sesión activa.', retry: false })
        return
      }
      try {
        const record = await getWeight(weightId, session.access, controller.signal)
        if (controller.signal.aborted || revision !== getSessionRevision()) return
        if (record.id !== weightId || record.animal_id !== animalId) {
          setState({ status: 'error', message: 'El pesaje no está disponible para este animal.', retry: false })
          return
        }
        setState({ status: 'ready', record })
      } catch (cause) {
        if (controller.signal.aborted || revision !== getSessionRevision()) return
        const status = cause instanceof ApiError ? cause.status : null
        setState({ status: 'error', retry: status === null || status >= 500,
          message: status === 404 ? 'El pesaje ya no está disponible o no fue encontrado.'
            : status === 401 ? 'La sesión ya no está disponible. Inicia sesión de nuevo.'
            : normalizeApiError(cause, 'No fue posible cargar el pesaje completo.').message })
      }
    }
    void load()
    return () => controller.abort()
  }, [weightId, animalId])

  if (state.status === 'loading') return <><p role="status">Cargando pesaje completo...</p><button type="button" onClick={onCancel}>Cancelar</button></>
  if (state.status === 'error') return <div><p role="alert">{state.message}</p>
    {state.retry && <button type="button" onClick={onRetry}>Reintentar consulta del pesaje</button>}
    <button type="button" onClick={onCancel}>Cancelar</button></div>
  return <WeightEditForm key={state.record.id} record={state.record} animalId={animalId} birthDate={birthDate}
    methods={methods} catalogError={catalogError} onCancel={onCancel} onSaved={onSaved} onRecheck={onRecheck} />
}

export default WeightPreparation
