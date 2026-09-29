import { useEffect, useMemo, useState } from 'react'

import { getSession } from '../../auth/session'
import { getAnimalWeightHistory } from '../weights.service'
import type {
  WeightHistory as WeightHistoryItem,
  WeighingMethod,
} from '../types'
import './WeightHistory.css'

interface WeightHistoryProps {
  animalId: string
  methods: WeighingMethod[]
}

function formatDate(date: string): string {
  const [year, month, day] = date.split('-')

  if (!year || !month || !day) {
    return date
  }

  return `${day}/${month}/${year}`
}

function WeightHistory({ animalId, methods }: WeightHistoryProps) {
  const [weights, setWeights] = useState<WeightHistoryItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isActive = true

    async function loadWeightHistory() {
      const session = getSession()

      if (!session) {
        if (isActive) {
          setError('No hay una sesión activa.')
          setIsLoading(false)
        }

        return
      }

      try {
        const weightHistory = await getAnimalWeightHistory(animalId, session.access)

        if (isActive) {
          setWeights(weightHistory)
        }
      } catch {
        if (isActive) {
          setError('No fue posible cargar el historial de peso.')
        }
      } finally {
        if (isActive) {
          setIsLoading(false)
        }
      }
    }

    void loadWeightHistory()

    return () => {
      isActive = false
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
          {error}
        </p>
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
              </tr>
            </thead>

            <tbody>
              {weights.map((weight) => (
                <tr key={weight.id}>
                  <td>{formatDate(weight.date)}</td>
                  <td>{weight.weight} kg</td>
                  <td>
                    {methodNames.get(weight.weighing_method_id) ??
                      'Método no disponible'}
                  </td>
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
