import { type FormEvent, useEffect, useRef, useState } from 'react'

import type { Animal } from '../../animals/types'
import { getSession } from '../../auth/session'
import { animalLabel, breedingErrorMessage, createBreeding } from '../breeding.service'
import type { BreedingType } from '../types'
import './BreedingForm.css'

interface BreedingFormProps {
  animal: Animal
  types: BreedingType[]
  males: Animal[]
  disabled: boolean
  onSaved: () => void
}

function BreedingForm({ animal, types, males, disabled, onSaved }: BreedingFormProps) {
  const [typeId, setTypeId] = useState('')
  const [maleId, setMaleId] = useState('')
  const [date, setDate] = useState('')
  const [expectedBirth, setExpectedBirth] = useState('')
  const [technician, setTechnician] = useState('')
  const [notes, setNotes] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isActive = useRef(false)
  const submitting = useRef(false)
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

    syncToday()
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
    if (submitting.current || disabled || !isActive.current) return
    setError(null)

    if (!typeId || !date) {
      setError('Completa el tipo de reproducción y la fecha.')
      return
    }
    if (date > new Date().toISOString().slice(0, 10)) {
      setError('La fecha del evento reproductivo no puede ser futura.')
      return
    }
    if (expectedBirth && expectedBirth <= date) {
      setError('La fecha estimada de parto debe ser posterior a la fecha del evento reproductivo.')
      return
    }
    if (maleId && !males.some((male) => male.id === maleId)) {
      setError('Selecciona un macho disponible de la misma especie o deja el campo vacío.')
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
      await createBreeding({
        animal_id: animal.id,
        male_id: maleId || null,
        breeding_type_id: typeId,
        date,
        expected_birth: expectedBirth || null,
        technician: technician.trim(),
        notes: notes.trim(),
      }, session.access)
    } catch (cause) {
      if (isActive.current) {
        setError(breedingErrorMessage(cause, 'No fue posible registrar el evento reproductivo. Revisa los datos e intenta de nuevo.'))
      }
      return
    } finally {
      submitting.current = false
      if (isActive.current) setIsSubmitting(false)
    }

    if (!isActive.current) return
    setTypeId('')
    setMaleId('')
    setDate('')
    setExpectedBirth('')
    setTechnician('')
    setNotes('')
    onSaved()
  }

  return (
    <section className="breeding-form">
      <h3>Registrar evento reproductivo</h3>
      <p>Hembra actual: <strong>{animalLabel(animal)}</strong></p>
      <form onSubmit={handleSubmit}>
        <fieldset disabled={isSubmitting || disabled}>
          <div className="breeding-form__field">
            <label htmlFor="breeding-type">Tipo de reproducción</label>
            <select id="breeding-type" value={typeId} onChange={(event) => setTypeId(event.target.value)} required>
              <option value="">Selecciona un tipo</option>
              {types.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
            </select>
            {types.length === 0 && <p>No hay tipos de reproducción disponibles.</p>}
          </div>
          <div className="breeding-form__field">
            <label htmlFor="breeding-male">Macho (opcional)</label>
            <select id="breeding-male" value={maleId} onChange={(event) => setMaleId(event.target.value)}>
              <option value="">Sin macho</option>
              {males.map((male) => <option key={male.id} value={male.id}>{animalLabel(male)}</option>)}
            </select>
            {males.length === 0 && <p>No hay machos disponibles de la misma especie. Puedes guardar sin macho.</p>}
          </div>
          <div className="breeding-form__field">
            <label htmlFor="breeding-date">Fecha</label>
            <input id="breeding-date" type="date" value={date} max={today}
              onChange={(event) => setDate(event.target.value)} required />
          </div>
          <div className="breeding-form__field">
            <label htmlFor="breeding-expected-birth">Fecha estimada de parto (opcional)</label>
            <input id="breeding-expected-birth" type="date" value={expectedBirth}
              onChange={(event) => setExpectedBirth(event.target.value)} />
          </div>
          <div className="breeding-form__field">
            <label htmlFor="breeding-technician">Técnico (opcional)</label>
            <input id="breeding-technician" value={technician} onChange={(event) => setTechnician(event.target.value)} />
          </div>
          <div className="breeding-form__field breeding-form__wide">
            <label htmlFor="breeding-notes">Notas (opcional)</label>
            <textarea id="breeding-notes" rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} />
          </div>
          <button type="submit">{isSubmitting ? 'Guardando...' : 'Guardar evento reproductivo'}</button>
        </fieldset>
      </form>
      {error && <p role="alert">{error}</p>}
    </section>
  )
}

export default BreedingForm
