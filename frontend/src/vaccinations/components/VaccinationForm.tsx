import FieldError from '../../components/FieldError'
import { fieldErrorAttributes, normalizeApiError } from '../../lib/api-errors'
import { type FormEvent, useEffect, useRef, useState } from 'react'

import { getSession, getSessionRevision } from '../../auth/session'
import { ApiError } from '../../lib/api'
import { vaccinationFieldErrors } from '../validation'
import type { VaccinationUpdatePayload } from '../types'
import { vaccinationToday } from '../civil-date'
import { createVaccination } from '../vaccinations.service'
import './VaccinationForm.css'

interface VaccinationFormProps {
  animalId: string
  birthDate: string | null
  onSaved: () => void
  onUncertain: () => void
  onRecheck: () => void
  onBegin: () => boolean
  onSettled: () => void
  onDraftBegin: () => boolean
  onDraftCancel: () => void
}

function VaccinationForm({ animalId, birthDate, onSaved, onUncertain, onRecheck, onBegin, onSettled, onDraftBegin, onDraftCancel }: VaccinationFormProps) {
  const [name, setName] = useState('')
  const [date, setDate] = useState('')
  const [dose, setDose] = useState('')
  const [nextDate, setNextDate] = useState('')
  const [batch, setBatch] = useState('')
  const [veterinarian, setVeterinarian] = useState('')
  const [notes, setNotes] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const [blocked, setBlocked] = useState(false)
  const lifetime = useRef<AbortController | null>(null)
  const blockedRef = useRef(false)
  const submitting = useRef(false)
  const [today, setToday] = useState(() => vaccinationToday())
  const [draft, setDraft] = useState(false)

  function change(setValue: (value: string) => void, value: string) {
    if (submitting.current || blockedRef.current || !onDraftBegin()) return
    setDraft(true)
    setValue(value)
  }

  useEffect(() => {
    const controller = new AbortController()
    lifetime.current = controller
    function syncToday() {
      setToday(vaccinationToday())
    }

    function handleVisibilityChange() {
      if (document.visibilityState === 'visible') syncToday()
    }

    // Check the civil day without assuming a fixed UTC offset or midnight.
    const timer = setInterval(syncToday, 1000)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('focus', syncToday)
    return () => {
      controller.abort()
      lifetime.current = null
      clearInterval(timer)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('focus', syncToday)
    }
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const controller = lifetime.current
    if (submitting.current || blockedRef.current || !controller || controller.signal.aborted) return
    setFieldErrors({})
    setError(null)

    const payload: VaccinationUpdatePayload = {
      animal_id: animalId, vaccine_name: name.trim(), application_date: date,
      dose, next_application_date: nextDate || null, batch: batch.trim() || null,
      veterinarian: veterinarian.trim() || null, notes: notes.trim() || null,
    }
    const errors = vaccinationFieldErrors(payload, birthDate)
    if (Object.keys(errors).length) { setFieldErrors(errors); setError('Revisa los campos del formulario.'); return }
    const session = getSession()
    if (!session) {
      setError('No hay una sesión activa.')
      return
    }

    if (!onBegin()) return
    submitting.current = true
    const revision = getSessionRevision()
    const current = () => !controller.signal.aborted && revision === getSessionRevision()
    setIsSubmitting(true)
    try {
      await createVaccination(payload, session.access, controller.signal)
    } catch (cause) {
      if (current()) {
        const uncertain = !(cause instanceof ApiError) || cause.status >= 500
        const denied = cause instanceof ApiError && [401, 403, 404].includes(cause.status)
        blockedRef.current = uncertain || denied
        setBlocked(blockedRef.current)
        const normalized = normalizeApiError(cause, cause instanceof ApiError && cause.status === 401
          ? 'La sesión ya no está disponible. Inicia sesión de nuevo.' : 'No fue posible registrar la vacunación.')
        setError(uncertain ? 'Resultado incierto: no se puede confirmar si la vacunación fue registrada. Consulta el historial antes de decidir iniciar otro registro. No se repetirá POST automáticamente.' : normalized.message)
        setFieldErrors(normalized.fieldErrors)
        if (uncertain) onUncertain()
      }
      return
    } finally {
      submitting.current = false
      if (current()) {
        setIsSubmitting(false)
        if (!blockedRef.current) onSettled()
      }
    }

    if (!current()) return
    setName('')
    setDate('')
    setDose('')
    setNextDate('')
    setBatch('')
    setVeterinarian('')
    setNotes('')
    setDraft(false)
    onSaved()
  }

  return (
    <section className="vaccination-form">
      <h3>Registrar vacunación</h3>
      <form onSubmit={handleSubmit}>
        <fieldset disabled={isSubmitting || blocked}>
          <div className="vaccination-form__field">
            <label htmlFor="vaccination-name">Nombre de vacuna</label>
            <input id="vaccination-name" maxLength={150} {...fieldErrorAttributes(fieldErrors, 'vaccine_name', 'vaccination-name')} value={name} onChange={(event) => change(setName, event.target.value)} required />
            <FieldError errors={fieldErrors} field="vaccine_name" controlId="vaccination-name" />
          </div>
          <div className="vaccination-form__field">
            <label htmlFor="vaccination-date">Fecha de aplicación</label>
            <input id="vaccination-date" {...fieldErrorAttributes(fieldErrors, 'application_date', 'vaccination-date')} type="date" value={date} min={birthDate ?? undefined} max={today}
              onChange={(event) => change(setDate, event.target.value)} required />
            <FieldError errors={fieldErrors} field="application_date" controlId="vaccination-date" />
          </div>
          <div className="vaccination-form__field">
            <label htmlFor="vaccination-dose">Dosis</label>
            <input id="vaccination-dose" {...fieldErrorAttributes(fieldErrors, 'dose', 'vaccination-dose')} type="text" inputMode="decimal" value={dose}
              onChange={(event) => change(setDose, event.target.value)} required />
            <FieldError errors={fieldErrors} field="dose" controlId="vaccination-dose" />
          </div>
          <div className="vaccination-form__field">
            <label htmlFor="vaccination-next-date">Próxima aplicación (opcional)</label>
            <input id="vaccination-next-date" {...fieldErrorAttributes(fieldErrors, 'next_application_date', 'vaccination-next-date')} type="date" value={nextDate}
              onChange={(event) => change(setNextDate, event.target.value)} />
            <FieldError errors={fieldErrors} field="next_application_date" controlId="vaccination-next-date" />
          </div>
          <div className="vaccination-form__field">
            <label htmlFor="vaccination-batch">Lote (opcional)</label>
            <input id="vaccination-batch" maxLength={50} {...fieldErrorAttributes(fieldErrors, 'batch', 'vaccination-batch')} value={batch} onChange={(event) => change(setBatch, event.target.value)} />
            <FieldError errors={fieldErrors} field="batch" controlId="vaccination-batch" />
          </div>
          <div className="vaccination-form__field">
            <label htmlFor="vaccination-veterinarian">Veterinario (opcional)</label>
            <input id="vaccination-veterinarian" maxLength={150} {...fieldErrorAttributes(fieldErrors, 'veterinarian', 'vaccination-veterinarian')} value={veterinarian} onChange={(event) => change(setVeterinarian, event.target.value)} />
            <FieldError errors={fieldErrors} field="veterinarian" controlId="vaccination-veterinarian" />
          </div>
          <div className="vaccination-form__field vaccination-form__wide">
            <label htmlFor="vaccination-notes">Notas (opcional)</label>
            <textarea id="vaccination-notes" {...fieldErrorAttributes(fieldErrors, 'notes', 'vaccination-notes')} rows={3} value={notes} onChange={(event) => change(setNotes, event.target.value)} />
            <FieldError errors={fieldErrors} field="notes" controlId="vaccination-notes" />
          </div>
          <button type="submit">{isSubmitting ? 'Guardando...' : 'Guardar vacunación'}</button>
        </fieldset>
      </form>
      {error && <p role="alert">{error}</p>}
      {draft && !blocked && <button type="button" disabled={isSubmitting} onClick={() => { if (!submitting.current && !blockedRef.current) onDraftCancel() }}>Cancelar registro y limpiar borrador</button>}
      {blocked && <button type="button" disabled={isSubmitting} onClick={onRecheck}>Consultar historial</button>}
    </section>
  )
}

export default VaccinationForm
