import { type FormEvent, useEffect, useId, useRef, useState } from 'react'
import { getSession, getSessionRevision } from '../../auth/session'
import FieldError from '../../components/FieldError'
import { ApiError } from '../../lib/api'
import { fieldErrorAttributes, normalizeApiError } from '../../lib/api-errors'
import { vaccinationToday } from '../civil-date'
import { vaccinationFieldErrors } from '../validation'
import { getVaccination, updateVaccination } from '../vaccinations.service'
import { matchesVaccinationSnapshot, vaccinationSnapshot } from '../reconciliation'
import type { Vaccination, VaccinationUpdatePayload } from '../types'
import './VaccinationForm.css'

export default function VaccinationEditForm({ record, vaccinationId, animalId, birthDate, onSaved, onCancel, onRecheck }: {
  record: Vaccination; vaccinationId: string; animalId: string; birthDate: string | null
  onSaved: () => void; onCancel: () => void; onRecheck: () => void
}) {
  const prefix = useId()
  const [fields, setFields] = useState<VaccinationUpdatePayload>(() => ({
    animal_id: animalId, vaccine_name: record.vaccine_name, application_date: record.application_date,
    next_application_date: record.next_application_date, dose: record.dose,
    batch: record.batch, veterinarian: record.veterinarian, notes: record.notes,
  }))
  const [saving, setSaving] = useState(false)
  const [blocked, setBlocked] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [errors, setErrors] = useState<Record<string, string[]>>({})
  const [today, setToday] = useState(() => vaccinationToday())
  const [uncertain, setUncertain] = useState(false)
  const [reconciling, setReconciling] = useState(false)
  const attempt = useRef<{ snapshot: Readonly<VaccinationUpdatePayload>; revision: number } | null>(null)
  const busy = useRef(false)
  const blockedRef = useRef(false)
  const lifetime = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    lifetime.current = controller
    const sync = () => setToday(vaccinationToday())
    const visible = () => { if (document.visibilityState === 'visible') sync() }
    const timer = setInterval(sync, 1000)
    window.addEventListener('focus', sync)
    document.addEventListener('visibilitychange', visible)
    return () => { controller.abort(); lifetime.current = null; clearInterval(timer); window.removeEventListener('focus', sync); document.removeEventListener('visibilitychange', visible) }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const controller = lifetime.current
    if (busy.current || blockedRef.current || !controller || controller.signal.aborted) return
    if (record.id !== vaccinationId || record.animal_id !== animalId || fields.animal_id !== animalId || !record.is_active) {
      blockedRef.current = true; setBlocked(true); setError('La vacunación no está disponible para este animal.'); return
    }
    const validation = vaccinationFieldErrors(fields, birthDate)
    setErrors(validation); setError(null)
    if (Object.keys(validation).length) { setError('Revisa los campos del formulario.'); return }
    const session = getSession()
    if (!session) { setError('No hay una sesión activa.'); return }
    const revision = getSessionRevision()
    const payload = { ...fields }
    const snapshot = vaccinationSnapshot(payload)
    const current = () => !controller.signal.aborted && revision === getSessionRevision()
    busy.current = true; setSaving(true)
    try {
      await updateVaccination(vaccinationId, payload, session.access, controller.signal)
      if (current()) { blockedRef.current = true; setBlocked(true); onSaved() }
    } catch (cause) {
      if (!current()) return
      const status = cause instanceof ApiError ? cause.status : null
      const uncertain = status === null || status >= 500
      if (uncertain) { attempt.current = { snapshot, revision }; setUncertain(true) }
      blockedRef.current = uncertain || [401, 403, 404].includes(status ?? 0)
      setBlocked(blockedRef.current)
      const normalized = normalizeApiError(cause, status === 404 ? 'La vacunación ya no está disponible o no fue encontrada.'
        : status === 401 ? 'La sesión ya no está disponible. Inicia sesión de nuevo.' : 'No fue posible actualizar la vacunación.')
      setError(uncertain ? 'No se pudo confirmar el resultado de la actualización. Consulta el registro para comprobar si los cambios quedaron aplicados. No se repetirá PUT automáticamente.' : normalized.message)
      setErrors(normalized.fieldErrors)
    } finally {
      busy.current = false
      if (current()) setSaving(false)
    }
  }

  async function reconcile() {
    const pending = attempt.current
    const controller = lifetime.current
    if (busy.current || !pending || !controller || controller.signal.aborted) return
    const current = () => !controller.signal.aborted && pending.revision === getSessionRevision()
    if (!current() || pending.snapshot.animal_id !== animalId) return
    const session = getSession()
    if (!session) return
    busy.current = true
    setReconciling(true)
    try {
      const persisted = await getVaccination(vaccinationId, animalId, session.access, controller.signal)
      if (!current()) return
      const matched = matchesVaccinationSnapshot(persisted, vaccinationId, pending.snapshot)
      attempt.current = null
      setUncertain(false)
      if (matched) {
        // Keep the guard until the confirmed-success callback unmounts this form.
        onSaved()
      } else {
        setFields({ ...vaccinationSnapshot(persisted) })
        setErrors({})
        setError('El registro consultado no coincide con los cambios intentados. Se cargaron los valores actuales; revisa los campos antes de volver a guardar.')
        blockedRef.current = false
        setBlocked(false)
      }
    } catch (cause) {
      if (current()) setError(normalizeApiError(cause, 'No fue posible reconciliar la actualización. El resultado sigue incierto; reintenta solamente la consulta del registro.').message)
    } finally {
      busy.current = false
      if (current()) setReconciling(false)
    }
  }

  const labels = { vaccine_name: 'Nombre de vacuna', application_date: 'Fecha de aplicación', next_application_date: 'Próxima aplicación (opcional)', dose: 'Dosis', batch: 'Lote (opcional)', veterinarian: 'Veterinario (opcional)', notes: 'Notas (opcional)' }
  return <section className="vaccination-form" aria-label="Editar vacunación" aria-busy={saving || reconciling}>
    <h3>Editar vacunación</h3><p>Vacunación: {vaccinationId}. Animal: {animalId}.</p>
    <form onSubmit={submit}><fieldset disabled={saving || blocked}>
      {(Object.keys(labels) as Array<keyof typeof labels>).map((field) => {
        const id = `${prefix}-${field}`
        const attrs = fieldErrorAttributes(errors, field, id)
        return <div key={field} className="vaccination-form__field"><label htmlFor={id}>{labels[field]}</label>
          {field === 'notes' ? <textarea id={id} value={fields.notes ?? ''} rows={3} {...attrs}
            onChange={(event) => setFields((old) => ({ ...old, notes: event.target.value }))} />
            : <input id={id} value={fields[field] ?? ''} {...attrs}
              type={field === 'application_date' || field === 'next_application_date' ? 'date' : 'text'}
              inputMode={field === 'dose' ? 'decimal' : undefined}
              required={['vaccine_name', 'application_date', 'dose'].includes(field)}
              maxLength={field === 'vaccine_name' || field === 'veterinarian' ? 150 : field === 'batch' ? 50 : undefined}
              min={field === 'application_date' ? birthDate ?? undefined : undefined}
              max={field === 'application_date' ? today : undefined}
              onChange={(event) => setFields((old) => ({ ...old, [field]: field === 'next_application_date' ? event.target.value || null : event.target.value }))} />}
          <FieldError errors={errors} field={field} controlId={id} />
        </div>
      })}
      <button type="submit">{saving ? 'Guardando...' : 'Guardar cambios'}</button>
    </fieldset></form>
    {!blocked && <button type="button" disabled={saving} onClick={() => { if (!busy.current) onCancel() }}>Cancelar</button>}
    {saving && <p role="status">Guardando cambios...</p>}
    {error && <p role="alert">{error}</p>}
    {reconciling && <p role="status">Consultando el registro para reconciliar la actualización...</p>}
    {blocked && (uncertain
      ? <button type="button" disabled={saving || reconciling} onClick={() => { void reconcile() }}>Consultar registro para reconciliar</button>
      : <button type="button" disabled={saving} onClick={onRecheck}>Consultar historial y cerrar edición</button>)}
  </section>
}
