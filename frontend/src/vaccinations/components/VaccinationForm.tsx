import { type FormEvent, useEffect, useRef, useState } from 'react'

import { getSession } from '../../auth/session'
import { createVaccination, vaccinationErrorMessage } from '../vaccinations.service'
import './VaccinationForm.css'

interface VaccinationFormProps {
  animalId: string
  onSaved: () => void
}

function VaccinationForm({ animalId, onSaved }: VaccinationFormProps) {
  const [name, setName] = useState('')
  const [date, setDate] = useState('')
  const [dose, setDose] = useState('')
  const [nextDate, setNextDate] = useState('')
  const [batch, setBatch] = useState('')
  const [veterinarian, setVeterinarian] = useState('')
  const [notes, setNotes] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const isActive = useRef(false)
  const submitting = useRef(false)
  // Match the backend's timezone.localdate() with TIME_ZONE = UTC.
  const [today, setToday] = useState(() => new Date().toISOString().slice(0, 10))

  useEffect(() => {
    isActive.current = true
    let timer: ReturnType<typeof setTimeout>

    function scheduleMidnight() {
      const now = new Date()
      const midnight = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1)
      timer = setTimeout(syncToday, midnight - now.getTime())
    }

    function syncToday() {
      clearTimeout(timer)
      setToday(new Date().toISOString().slice(0, 10))
      scheduleMidnight()
    }

    function handleVisibilityChange() {
      if (document.visibilityState === 'visible') syncToday()
    }

    scheduleMidnight()
    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('focus', syncToday)
    return () => {
      isActive.current = false
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('focus', syncToday)
    }
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting.current) return
    setError(null)
    setSuccess(false)

    if (!name.trim() || !date || !dose.trim()) {
      setError('Completa el nombre de la vacuna, la fecha de aplicación y la dosis.')
      return
    }
    if (!Number.isFinite(Number(dose)) || Number(dose) <= 0) {
      setError('La dosis debe ser un número mayor que cero.')
      return
    }
    if (date > new Date().toISOString().slice(0, 10)) {
      setError('La fecha de aplicación no puede ser futura.')
      return
    }
    if (nextDate && nextDate <= date) {
      setError('La próxima fecha de aplicación debe ser posterior a la fecha de aplicación.')
      return
    }
    const session = getSession()
    if (!session) {
      setError('No hay una sesión activa.')
      return
    }

    submitting.current = true
    setIsSubmitting(true)
    try {
      await createVaccination({
        animal_id: animalId,
        vaccine_name: name.trim(),
        application_date: date,
        dose,
        next_application_date: nextDate || null,
        batch: batch.trim() || null,
        veterinarian: veterinarian.trim() || null,
        notes: notes.trim() || null,
      }, session.access)
    } catch (cause) {
      if (isActive.current) {
        setError(vaccinationErrorMessage(cause, 'No fue posible registrar la vacunación. Revisa los datos e intenta de nuevo.'))
      }
      return
    } finally {
      submitting.current = false
      if (isActive.current) setIsSubmitting(false)
    }

    if (!isActive.current) return
    setName('')
    setDate('')
    setDose('')
    setNextDate('')
    setBatch('')
    setVeterinarian('')
    setNotes('')
    setSuccess(true)
    onSaved()
  }

  return (
    <section className="vaccination-form">
      <h3>Registrar vacunación</h3>
      <form onSubmit={handleSubmit}>
        <fieldset disabled={isSubmitting}>
          <div className="vaccination-form__field">
            <label htmlFor="vaccination-name">Nombre de vacuna</label>
            <input id="vaccination-name" value={name} onChange={(event) => setName(event.target.value)} required />
          </div>
          <div className="vaccination-form__field">
            <label htmlFor="vaccination-date">Fecha de aplicación</label>
            <input id="vaccination-date" type="date" value={date} max={today}
              onChange={(event) => setDate(event.target.value)} required />
          </div>
          <div className="vaccination-form__field">
            <label htmlFor="vaccination-dose">Dosis</label>
            <input id="vaccination-dose" type="number" step="any" min="0" value={dose}
              onChange={(event) => setDose(event.target.value)} required />
          </div>
          <div className="vaccination-form__field">
            <label htmlFor="vaccination-next-date">Próxima aplicación (opcional)</label>
            <input id="vaccination-next-date" type="date" value={nextDate}
              onChange={(event) => setNextDate(event.target.value)} />
          </div>
          <div className="vaccination-form__field">
            <label htmlFor="vaccination-batch">Lote (opcional)</label>
            <input id="vaccination-batch" value={batch} onChange={(event) => setBatch(event.target.value)} />
          </div>
          <div className="vaccination-form__field">
            <label htmlFor="vaccination-veterinarian">Veterinario (opcional)</label>
            <input id="vaccination-veterinarian" value={veterinarian} onChange={(event) => setVeterinarian(event.target.value)} />
          </div>
          <div className="vaccination-form__field vaccination-form__wide">
            <label htmlFor="vaccination-notes">Notas (opcional)</label>
            <textarea id="vaccination-notes" rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} />
          </div>
          <button type="submit">{isSubmitting ? 'Guardando...' : 'Guardar vacunación'}</button>
        </fieldset>
      </form>
      {error && <p role="alert">{error}</p>}
      {success && <p className="vaccination-form__success" role="status">Vacunación registrada correctamente.</p>}
    </section>
  )
}

export default VaccinationForm
