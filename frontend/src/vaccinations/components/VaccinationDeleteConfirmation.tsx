import { useEffect, useRef, useState } from 'react'
import { useCurrentContext } from '../../auth/current-context'
import { getSession, getSessionRevision } from '../../auth/session'
import { ApiError } from '../../lib/api'
import { normalizeApiError } from '../../lib/api-errors'
import { deleteVaccination, getVaccination } from '../vaccinations.service'
import type { Vaccination } from '../types'
import './VaccinationForm.css'

type Props = {
  vaccinationId: string; animalId: string
  onCancel: () => void; onDeleted: () => void; onUnavailable: () => void
}

export default function VaccinationDeleteConfirmation(props: Props) {
  const { canWrite, currentOrganization } = useCurrentContext()
  return canWrite && currentOrganization ? <Confirmation key={`${currentOrganization.id}:${props.animalId}:${props.vaccinationId}`} {...props} /> : null
}

function Confirmation({ vaccinationId, animalId, onCancel, onDeleted, onUnavailable }: Props) {
  const [record, setRecord] = useState<Vaccination | null>(null)
  const [pending, setPending] = useState(true)
  const [uncertain, setUncertain] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const lifetime = useRef<AbortController | null>(null)
  const revision = useRef(getSessionRevision())
  const busy = useRef(false)
  const consumed = useRef(false)
  const unresolved = useRef(false)
  const finished = useRef(false)

  const current = (controller: AbortController) => !controller.signal.aborted && revision.current === getSessionRevision()

  async function read(controller: AbortController) {
    if (busy.current || finished.current || !current(controller)) return
    const session = getSession()
    if (!session) { setPending(false); setError('No hay una sesión activa.'); return }
    busy.current = true
    setPending(true)
    setError(null)
    try {
      const data = await getVaccination(vaccinationId, animalId, session.access, controller.signal)
      if (!current(controller)) return
      setRecord(data)
      if (unresolved.current) setNotice('La vacunación sigue disponible. No se confirmó la eliminación; puedes realizar una nueva confirmación explícita.')
      unresolved.current = false
      consumed.current = false
      setUncertain(false)
    } catch (cause) {
      if (!current(controller)) return
      if (cause instanceof ApiError && cause.status === 404) { finished.current = true; onUnavailable(); return }
      setError(normalizeApiError(cause, 'No fue posible consultar una vacunación válida. Reintenta solamente la consulta.').message)
    } finally {
      busy.current = false
      if (current(controller)) setPending(false)
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    lifetime.current = controller
    queueMicrotask(() => { void read(controller) })
    return () => { controller.abort(); lifetime.current = null }
    // The keyed confirmation owns one identity and context for its lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function confirm() {
    const controller = lifetime.current
    if (!controller || !current(controller) || busy.current || consumed.current || finished.current || !record) return
    if (record.id !== vaccinationId || record.animal_id !== animalId || record.is_active !== true) return
    const session = getSession()
    if (!session) { setError('No hay una sesión activa.'); return }
    consumed.current = true
    busy.current = true
    setPending(true)
    setError(null)
    try {
      await deleteVaccination(vaccinationId, session.access, controller.signal)
      if (current(controller)) { finished.current = true; onDeleted() }
    } catch (cause) {
      if (!current(controller)) return
      unresolved.current = true
      setUncertain(true)
      const unknown = !(cause instanceof ApiError) || cause.status >= 500
      setError(unknown
        ? 'No se pudo confirmar la eliminación. Consulta el registro; no se repetirá DELETE automáticamente.'
        : cause.status === 404 ? 'No se confirmó esta eliminación. Consulta si la vacunación sigue disponible.'
          : normalizeApiError(cause, 'No fue posible eliminar la vacunación. Consulta el registro antes de continuar.').message)
    } finally {
      busy.current = false
      if (current(controller)) setPending(false)
    }
  }

  return <section className="vaccination-form" aria-label="Confirmar eliminación de vacunación" aria-busy={pending}>
    <h3>Eliminar vacunación</h3>
    {record && <p>Vacuna: <strong>{record.vaccine_name}</strong>. Fecha: <time dateTime={record.application_date}>{record.application_date.split('-').reverse().join('/')}</time>. Dosis: <strong>{record.dose}</strong>. Vacunación: {vaccinationId}.</p>}
    <p>Se eliminará del historial activo mediante borrado lógico. No existe restauración desde esta interfaz.</p>
    {pending && <p role="status">Procesando consulta o eliminación...</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
    {!uncertain && <button type="button" disabled={pending} onClick={() => { const controller = lifetime.current; if (controller && current(controller) && !busy.current && !finished.current) onCancel() }}>Cancelar</button>}
    {record && !uncertain && <button type="button" disabled={pending} onClick={() => { void confirm() }}>Confirmar eliminación</button>}
    {(uncertain || (!record && !pending)) && <button type="button" disabled={pending} onClick={() => { const controller = lifetime.current; if (controller) void read(controller) }}>Consultar registro</button>}
  </section>
}
