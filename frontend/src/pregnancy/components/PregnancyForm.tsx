import { type FormEvent, useEffect, useRef, useState } from 'react'

import type { Animal } from '../../animals/types'
import type { BreedingEvent } from '../../breeding/types'
import type { PregnancyCreatePayload } from '../types'
import './PregnancyForm.css'

interface PregnancyFormProps {
  animal: Animal
  events: BreedingEvent[]
  eventLabels: Map<string, string>
  disabled: boolean
  onCreate: (payload: PregnancyCreatePayload) => Promise<boolean>
}

function PregnancyForm({ animal, events, eventLabels, disabled, onCreate }: PregnancyFormProps) {
  const [breedingId, setBreedingId] = useState('')
  const [diagnosisDate, setDiagnosisDate] = useState('')
  const [expectedBirth, setExpectedBirth] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [today, setToday] = useState(() => new Date().toISOString().slice(0, 10))
  const active = useRef(false)
  const submitting = useRef(false)
  const selected = events.find((event) => event.id === breedingId)
  const invalidDiagnosis = Boolean(selected && diagnosisDate && diagnosisDate < selected.date)

  useEffect(() => {
    active.current = true
    let timer: ReturnType<typeof setTimeout>
    function syncToday() {
      clearTimeout(timer)
      const now = new Date()
      setToday(now.toISOString().slice(0, 10))
      const midnight = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1)
      timer = setTimeout(syncToday, midnight - now.getTime())
    }
    function handleVisibilityChange() {
      if (document.visibilityState === 'visible') syncToday()
    }
    syncToday()
    window.addEventListener('focus', syncToday)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      active.current = false
      clearTimeout(timer)
      window.removeEventListener('focus', syncToday)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [])

  function selectEvent(id: string) {
    setBreedingId(id)
    setExpectedBirth(events.find((event) => event.id === id)?.expected_birth ?? '')
    setError(null)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!active.current || submitting.current || disabled) return
    setError(null)
    if (!selected || !diagnosisDate || !expectedBirth) {
      setError('Selecciona un evento disponible y completa las fechas de diagnóstico y parto estimado.')
      return
    }
    if (diagnosisDate < selected.date) {
      setError('La fecha de diagnóstico no puede ser anterior al evento reproductivo.')
      return
    }
    if (diagnosisDate > new Date().toISOString().slice(0, 10)) {
      setError('La fecha de diagnóstico no puede ser futura.')
      return
    }
    if (expectedBirth <= diagnosisDate) {
      setError('La fecha estimada de parto debe ser posterior a la fecha de diagnóstico.')
      return
    }
    submitting.current = true
    try {
      const saved = await onCreate({
        breeding_id: selected.id,
        animal_id: animal.id,
        diagnosis_date: diagnosisDate,
        expected_birth: expectedBirth,
        confirmed: true,
        notes: notes.trim() || null,
      })
      if (saved && active.current) {
        setBreedingId('')
        setDiagnosisDate('')
        setExpectedBirth('')
        setNotes('')
      }
    } finally {
      submitting.current = false
    }
  }

  return <section className="pregnancy-form">
    <h3>Registrar gestación confirmada</h3>
    <p>Animal actual: <strong>{[animal.name?.trim(), animal.internal_id?.trim()].filter(Boolean).join(' · ') || 'Sin identificación'}</strong></p>
    {!animal.is_active && <p>El registro está disponible únicamente para animales activos.</p>}
    {events.length === 0 && <p>No hay eventos reproductivos disponibles para registrar una gestación.</p>}
    <form onSubmit={handleSubmit}>
      <fieldset disabled={disabled || events.length === 0}>
        <div className="pregnancy-form__field pregnancy-form__wide">
          <label htmlFor="pregnancy-breeding">Evento reproductivo</label>
          <select id="pregnancy-breeding" value={selected ? breedingId : ''} onChange={(event) => selectEvent(event.target.value)} required>
            <option value="">Selecciona un evento</option>
            {events.map((event) => <option key={event.id} value={event.id}>{eventLabels.get(event.id) ?? 'Evento reproductivo'}</option>)}
          </select>
          {breedingId && !selected && <p role="alert">El evento seleccionado ya no está disponible. Selecciona otro evento.</p>}
        </div>
        <div className="pregnancy-form__field">
          <label htmlFor="pregnancy-diagnosis">Fecha de diagnóstico</label>
          <input id="pregnancy-diagnosis" type="date" value={diagnosisDate} min={selected?.date} max={today}
            aria-invalid={invalidDiagnosis || undefined} aria-describedby={invalidDiagnosis ? 'pregnancy-diagnosis-error' : undefined}
            onChange={(event) => setDiagnosisDate(event.target.value)} required />
          {invalidDiagnosis && <p id="pregnancy-diagnosis-error" role="alert">La fecha de diagnóstico no puede ser anterior al evento seleccionado.</p>}
        </div>
        <div className="pregnancy-form__field">
          <label htmlFor="pregnancy-expected-birth">Fecha estimada de parto</label>
          <input id="pregnancy-expected-birth" type="date" value={expectedBirth}
            onChange={(event) => setExpectedBirth(event.target.value)} required />
        </div>
        <div className="pregnancy-form__field pregnancy-form__wide">
          <label htmlFor="pregnancy-notes">Notas (opcional)</label>
          <textarea id="pregnancy-notes" rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} />
        </div>
        <button type="submit">Guardar gestación</button>
      </fieldset>
    </form>
    {error && <p role="alert">{error}</p>}
  </section>
}

export default PregnancyForm
