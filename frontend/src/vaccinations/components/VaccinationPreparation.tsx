import { useEffect, useState } from 'react'
import { getSession, getSessionRevision } from '../../auth/session'
import { ApiError } from '../../lib/api'
import { normalizeApiError } from '../../lib/api-errors'
import { getVaccination } from '../vaccinations.service'
import type { Vaccination } from '../types'
import VaccinationEditForm from './VaccinationEditForm'
import WriteOnly from '../../auth/WriteOnly'

type Props = {
  vaccinationId: string; animalId: string; birthDate: string | null
  onCancel: () => void; onSaved: () => void; onRecheck: () => void
  readOnly?: boolean
}

export default function VaccinationPreparation(props: Props) {
  const [attempt, setAttempt] = useState(0)
  return <LoadedVaccination key={attempt} {...props} onRetry={() => setAttempt((value) => value + 1)} />
}

function LoadedVaccination({ vaccinationId, animalId, birthDate, onCancel, onSaved, onRecheck, onRetry, readOnly }: Props & { onRetry: () => void }) {
  const [state, setState] = useState<{ status: 'loading' } | { status: 'error'; message: string; retry: boolean } | { status: 'ready'; record: Vaccination }>({ status: 'loading' })
  useEffect(() => {
    const controller = new AbortController()
    const revision = getSessionRevision()
    const current = () => !controller.signal.aborted && revision === getSessionRevision()
    async function load() {
      const session = getSession()
      if (!session) { setState({ status: 'error', message: 'No hay una sesión activa.', retry: false }); return }
      try {
        const record = await getVaccination(vaccinationId, animalId, session.access, controller.signal)
        if (current()) setState({ status: 'ready', record })
      } catch (cause) {
        if (!current()) return
        const status = cause instanceof ApiError ? cause.status : null
        setState({ status: 'error', retry: cause instanceof ApiError ? cause.status >= 500 : cause instanceof TypeError,
          message: status === 404 ? 'La vacunación ya no está disponible o no fue encontrada.'
            : status === 401 ? 'La sesión ya no está disponible. Inicia sesión de nuevo.'
            : normalizeApiError(cause, 'No fue posible obtener un detalle válido para esta vacunación y animal.').message })
      }
    }
    void load()
    return () => controller.abort()
  }, [vaccinationId, animalId])
  if (state.status === 'loading') return <section><p role="status">Cargando vacunación completa...</p><button type="button" onClick={onCancel}>Cancelar</button></section>
  if (state.status === 'error') return <section><p role="alert">{state.message}</p>
    {state.retry && <button type="button" onClick={onRetry}>Reintentar consulta del detalle</button>}
    <button type="button" onClick={onCancel}>Volver</button></section>
  if (readOnly) {
    const record = state.record
    return <section aria-label="Detalle de vacunación">
      <h3>Detalle de vacunación</h3>
      <dl>
        <div><dt>Vacuna</dt><dd>{record.vaccine_name}</dd></div>
        <div><dt>Fecha de aplicación</dt><dd>{record.application_date}</dd></div>
        <div><dt>Próxima aplicación</dt><dd>{record.next_application_date ?? '—'}</dd></div>
        <div><dt>Dosis</dt><dd>{record.dose}</dd></div>
        <div><dt>Lote</dt><dd>{record.batch || '—'}</dd></div>
        <div><dt>Veterinario</dt><dd>{record.veterinarian || '—'}</dd></div>
        <div><dt>Notas</dt><dd>{record.notes || '—'}</dd></div>
        <div><dt>Estado</dt><dd>{record.is_active ? 'Activa' : 'Inactiva'}</dd></div>
      </dl>
      <button type="button" onClick={onCancel}>Volver</button>
    </section>
  }
  return <WriteOnly><VaccinationEditForm record={state.record} vaccinationId={vaccinationId} animalId={animalId} birthDate={birthDate}
    onCancel={onCancel} onSaved={onSaved} onRecheck={onRecheck} /></WriteOnly>
}
