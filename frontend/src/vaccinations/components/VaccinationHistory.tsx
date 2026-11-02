import { useEffect, useState } from 'react'
import WriteOnly from '../../auth/WriteOnly'

import { getSession, getSessionRevision } from '../../auth/session'
import type { Vaccination } from '../types'
import { getAnimalVaccinationHistory, vaccinationErrorMessage } from '../vaccinations.service'
import './VaccinationHistory.css'

interface VaccinationHistoryProps {
  animalId: string
  saved: 'created' | 'updated' | 'deleted' | null
  excludedIds?: string[]
  actionsDisabled: boolean
  onEdit: (id: string) => void
  onView: (id: string) => void
  onDelete: (id: string) => void
  onLoaded: () => void
}

function formatDate(date: string) {
  return date.split('-').reverse().join('/')
}

function VaccinationHistory({ animalId, saved, actionsDisabled, onEdit, onView, onDelete, onLoaded, excludedIds = [] }: VaccinationHistoryProps) {
  const [history, setHistory] = useState<Vaccination[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const revision = getSessionRevision()
    const current = () => !controller.signal.aborted && revision === getSessionRevision()

    async function load() {
      setIsLoading(true)
      setError(null)
      const session = getSession()
      if (!session) {
        setError('No hay una sesión activa.')
        setIsLoading(false)
        return
      }
      try {
        const data = await getAnimalVaccinationHistory(animalId, session.access, controller.signal)
        if (current()) { setHistory(data); onLoaded() }
      } catch (cause) {
        if (current()) {
          setError(vaccinationErrorMessage(cause, 'No fue posible cargar el historial de vacunaciones.'))
        }
      } finally {
        if (current()) setIsLoading(false)
      }
    }

    void load()
    return () => controller.abort()
  }, [animalId, attempt, onLoaded])

  return (
    <section className="vaccination-history">
      <h3>Historial de vacunaciones</h3>
      {isLoading ? <p role="status">Cargando vacunaciones...</p> : error ? (
        <div>
          {saved && <p role="status">La vacunación fue {saved === 'deleted' ? 'eliminada' : saved === 'updated' ? 'actualizada' : 'registrada'}, pero no se pudo actualizar el historial. Reintenta solamente la consulta.</p>}
          <p role="alert">{error}</p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>Actualizar historial</button>
        </div>
      ) : history.filter((item) => !excludedIds.includes(item.id)).length === 0 ? <p>Todavía no hay vacunaciones para este animal.</p> : (
        <div className="vaccination-history__table-wrapper">
          <table className="vaccination-history__cards" role="table">
            <thead>
              <tr><th scope="col">Fecha de aplicación</th><th scope="col">Vacuna</th><th scope="col">Dosis</th><th scope="col">Próxima aplicación</th><th scope="col">Acciones</th></tr>
            </thead>
            <tbody role="rowgroup">
              {history.filter((item) => !excludedIds.includes(item.id)).sort((a, b) => b.application_date.localeCompare(a.application_date)).map((item) => (
                <tr role="row" key={item.id}>
                  <td data-label="Fecha de aplicación" role="cell">{formatDate(item.application_date)}</td>
                  <td data-label="Vacuna" role="cell">
                    {item.vaccine_name}
                  </td>
                  <td data-label="Dosis" role="cell">{item.dose}</td>
                  <td data-label="Próxima aplicación" role="cell">{item.next_application_date ? formatDate(item.next_application_date) : '—'}</td>
                  <td className="vaccination-history__actions" data-label="Acciones" role="cell">
                    <button type="button" disabled={actionsDisabled} onClick={() => onView(item.id)}>Ver detalles</button>
                    <WriteOnly><button type="button" disabled={actionsDisabled} onClick={() => onEdit(item.id)}>Editar</button></WriteOnly>
                    <WriteOnly><button type="button" disabled={actionsDisabled} onClick={() => onDelete(item.id)}>Eliminar</button></WriteOnly>
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

export default VaccinationHistory
