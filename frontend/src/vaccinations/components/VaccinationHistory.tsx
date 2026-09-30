import { useEffect, useState } from 'react'

import { getSession } from '../../auth/session'
import type { Vaccination } from '../types'
import { getAnimalVaccinationHistory, vaccinationErrorMessage } from '../vaccinations.service'
import './VaccinationHistory.css'

interface VaccinationHistoryProps {
  animalId: string
  version: number
}

function formatDate(date: string) {
  return date.split('-').reverse().join('/')
}

function VaccinationHistory({ animalId, version }: VaccinationHistoryProps) {
  const [history, setHistory] = useState<Vaccination[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

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
        if (!controller.signal.aborted) setHistory(data)
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(vaccinationErrorMessage(cause, 'No fue posible cargar el historial de vacunaciones.'))
        }
      } finally {
        if (!controller.signal.aborted) setIsLoading(false)
      }
    }

    void load()
    return () => controller.abort()
  }, [animalId, version, attempt])

  return (
    <section className="vaccination-history">
      <h3>Historial de vacunaciones</h3>
      {isLoading ? <p role="status">Cargando vacunaciones...</p> : error ? (
        <div>
          {version > 0 && <p role="status">La vacunación se guardó. Actualiza el historial; no necesitas volver a registrarla.</p>}
          <p role="alert">{error}</p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>Actualizar historial</button>
        </div>
      ) : history.length === 0 ? <p>Todavía no hay vacunaciones para este animal.</p> : (
        <div className="vaccination-history__table-wrapper">
          <table>
            <thead>
              <tr><th scope="col">Fecha de aplicación</th><th scope="col">Vacuna</th><th scope="col">Dosis</th><th scope="col">Próxima aplicación</th></tr>
            </thead>
            <tbody>
              {history.map((item) => (
                <tr key={item.id}>
                  <td>{formatDate(item.application_date)}</td>
                  <td>
                    {item.vaccine_name}
                    {(item.batch?.trim() || item.veterinarian?.trim() || item.notes?.trim()) && (
                      <details>
                        <summary>Ver detalles</summary>
                        <dl>
                          {item.batch?.trim() && <div><dt>Lote</dt><dd>{item.batch}</dd></div>}
                          {item.veterinarian?.trim() && <div><dt>Veterinario</dt><dd>{item.veterinarian}</dd></div>}
                          {item.notes?.trim() && <div><dt>Notas</dt><dd>{item.notes}</dd></div>}
                        </dl>
                      </details>
                    )}
                  </td>
                  <td>{item.dose}</td>
                  <td>{item.next_application_date ? formatDate(item.next_application_date) : '—'}</td>
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
