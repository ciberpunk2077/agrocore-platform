import { useEffect, useMemo, useRef, useState } from 'react'

import WriteOnly from '../../auth/WriteOnly'
import { getSession, getSessionRevision } from '../../auth/session'
import { normalizeApiError } from '../../lib/api-errors'
import WeightPreparation from './WeightPreparation'
import WeightDeleteConfirmation from './WeightDeleteConfirmation'
import { getAnimalWeightHistory, getWeighingMethods } from '../weights.service'
import type {
  WeightHistory as WeightHistoryItem,
  WeighingMethod,
} from '../types'
import './WeightHistory.css'

interface WeightHistoryProps {
  animalId: string
  birthDate: string | null
}

function formatDate(date: string): string {
  const [year, month, day] = date.split('-')

  if (!year || !month || !day) {
    return date
  }

  return `${day}/${month}/${year}`
}

function WeightHistory(props: WeightHistoryProps) {
  return <WeightHistorySession key={props.animalId} {...props} />
}

function WeightHistorySession(props: WeightHistoryProps) {
  const [attempt, setAttempt] = useState(0)
  const [saved, setSaved] = useState<'updated' | 'deleted' | null>(null)
  return <>
    {saved === 'updated' && <p role="status">El pesaje se actualizó correctamente.</p>}
    {saved === 'deleted' && <p role="status">El pesaje se eliminó correctamente. Dejará de aparecer en el historial.</p>}
    <AnimalWeightHistory key={attempt} {...props} saved={saved}
      onUpdated={() => { setSaved('updated'); setAttempt((value) => value + 1) }}
      onDeleted={() => { setSaved('deleted'); setAttempt((value) => value + 1) }}
      onRetry={() => setAttempt((value) => value + 1)} />
  </>
}

function AnimalWeightHistory({ animalId, birthDate, saved, onUpdated, onDeleted, onRetry }: WeightHistoryProps & {
  saved: 'updated' | 'deleted' | null; onUpdated: () => void; onDeleted: () => void; onRetry: () => void
}) {
  const [methods, setMethods] = useState<WeighingMethod[]>([])
  const [weights, setWeights] = useState<WeightHistoryItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<WeightHistoryItem | null>(null)
  const actionsDisabled = selectedId !== null || deleting !== null
  const selectionLocked = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    const revision = getSessionRevision()

    async function loadWeightHistory() {
      const session = getSession()

      if (!session) {
        if (!controller.signal.aborted) {
          setError('No hay una sesión activa.')
          setIsLoading(false)
        }

        return
      }

      try {
        const [weightHistory, weighingMethods] = await Promise.allSettled([
          getAnimalWeightHistory(animalId, session.access, controller.signal),
          getWeighingMethods(session.access, controller.signal),
        ])

        if (controller.signal.aborted || revision !== getSessionRevision()) return
        if (weightHistory.status === 'rejected') {
          setError(normalizeApiError(weightHistory.reason, 'No fue posible cargar el historial de peso.').message)
        } else {
          setWeights(weightHistory.value)
        }
        if (weighingMethods.status === 'rejected') {
          setCatalogError(normalizeApiError(weighingMethods.reason, 'No fue posible cargar el catálogo de métodos de pesaje.').message)
        } else {
          setMethods(weighingMethods.value)
        }
      } finally {
        if (!controller.signal.aborted && revision === getSessionRevision()) {
          setIsLoading(false)
        }
      }
    }

    void loadWeightHistory()

    return () => {
      controller.abort()
    }
  }, [animalId])

  const methodNames = useMemo(
    () =>
      new Map(
        methods.map((method) => [
          method.id,
          method.name,
        ]),
      ),
    [methods],
  )

  if (isLoading) {
    return (
      <section className="weight-history">
        <h2>Historial de peso</h2>
        <p className="weight-history__message">
          Cargando historial de peso...
        </p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="weight-history">
        <h2>Historial de peso</h2>
        <p className="weight-history__message weight-history__message--error">
          {saved && `El pesaje fue ${saved === 'deleted' ? 'eliminado' : 'actualizado'}, pero no se pudo actualizar el historial. `}{error}
        </p>
        <button type="button" onClick={onRetry}>Reintentar consulta del historial</button>
      </section>
    )
  }

  return (
    <section className="weight-history">
      <div className="weight-history__header">
        <div>
          <h2>Historial de peso</h2>
          <p>Evolución registrada del peso del animal.</p>
        </div>
      </div>

      {catalogError && <p role="alert">{catalogError} Los pesos siguen disponibles; los nombres de métodos no se pudieron consultar.</p>}
      <WriteOnly>
        {deleting && <WeightDeleteConfirmation key={deleting.id} record={deleting}
          onDeleted={onDeleted} onRecheck={onRetry} onCancel={() => {
            selectionLocked.current = false
            setDeleting(null)
          }} />}
        {selectedId && <WeightPreparation key={selectedId} weightId={selectedId} animalId={animalId}
          methods={methods} birthDate={birthDate} catalogError={catalogError} onSaved={onUpdated} onRecheck={onRetry} onCancel={() => {
            selectionLocked.current = false
            setSelectedId(null)
          }} />}
      </WriteOnly>

      {weights.length === 0 ? (
        <div className="weight-history__empty">
          Todavía no hay registros de peso para este animal.
        </div>
      ) : (
        <div className="weight-history__table-wrapper">
          <table className="weight-history__table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Peso</th>
                <th>Método</th>
                <WriteOnly><th>Acciones</th></WriteOnly>
              </tr>
            </thead>

            <tbody>
              {weights.map((weight) => (
                <tr key={weight.id}>
                  <td>{formatDate(weight.date)}</td>
                  <td>{weight.weight} kg</td>
                  <td>
                    {catalogError ? 'Catálogo de métodos no disponible'
                      : methodNames.get(weight.weighing_method_id) ?? 'Método no disponible'}
                  </td>
                  <WriteOnly><td><button type="button" disabled={actionsDisabled} onClick={() => {
                    if (selectionLocked.current) return
                    selectionLocked.current = true
                    setSelectedId(weight.id)
                  }}>Editar</button>
                    <button type="button" disabled={actionsDisabled} onClick={() => {
                      if (selectionLocked.current) return
                      selectionLocked.current = true
                      setDeleting(weight)
                    }}>Eliminar</button></td></WriteOnly>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default WeightHistory
