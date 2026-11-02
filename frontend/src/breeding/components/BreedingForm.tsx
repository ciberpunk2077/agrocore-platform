import FieldError from '../../components/FieldError'
import { fieldErrorAttributes, normalizeApiError } from '../../lib/api-errors'
import { type FormEvent, useEffect, useRef, useState } from 'react'

import type { Animal } from '../../animals/types'
import { animalLabel } from '../breeding.service'
import type { BreedingCreatePayload, BreedingType } from '../types'
import { normalizedPayload, payloadError } from '../validation'
import './BreedingForm.css'

interface BreedingFormProps {
  animal: Animal
  types: BreedingType[]
  males: Animal[]
  disabled: boolean
  businessToday: string | null
  onCreate: (payload: BreedingCreatePayload) => Promise<boolean>
}

function BreedingForm({ animal, types, males, disabled, businessToday, onCreate }: BreedingFormProps) {
  const [typeId, setTypeId] = useState('')
  const [maleId, setMaleId] = useState('')
  const [date, setDate] = useState('')
  const [expectedBirth, setExpectedBirth] = useState('')
  const [technician, setTechnician] = useState('')
  const [notes, setNotes] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const isActive = useRef(false)
  const submitting = useRef(false)

  useEffect(() => {
    isActive.current = true
    return () => {
      isActive.current = false
    }
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFieldErrors({})
    if (submitting.current || disabled || !isActive.current) return
    setError(null)

    if (!businessToday) {
      setError('La fecha operativa de la organización no está disponible.')
      return
    }

    if (!typeId || !date) {
      setError('Completa el tipo de reproducción y la fecha.')
      return
    }
    if (date > businessToday) {
      setError('La fecha del evento reproductivo no puede ser futura.')
      return
    }
    if (expectedBirth && expectedBirth <= date) {
      setError('La fecha estimada de parto debe ser posterior a la fecha del evento reproductivo.')
      return
    }
    if (maleId && !males.some((male) => male.id === maleId)) {
      setError('Selecciona un macho disponible o deja el campo vacío.')
      return
    }
    const payload = normalizedPayload({ animal_id: animal.id, male_id: maleId || null, breeding_type_id: typeId,
      date, expected_birth: expectedBirth || null, technician: technician.trim(), notes: notes.trim() })
    const invalid = payloadError(payload, animal.id, businessToday)
    if (invalid || !types.some(type => type.id === typeId)) {
      setError(invalid ?? 'Selecciona un tipo de reproducción disponible.')
      return
    }

    submitting.current = true
    setIsSubmitting(true)
    try {
      if (!await onCreate(payload)) return
    } catch (cause) {
      if (isActive.current) {
        const normalized = normalizeApiError(cause, 'No fue posible registrar el evento reproductivo. Revisa los datos e intenta de nuevo.')
        setError(normalized.message)
        setFieldErrors(normalized.fieldErrors)
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
  }

  return (
    <section className="breeding-form">
      <h3>Registrar evento reproductivo</h3>
      <p>Hembra actual: <strong>{animalLabel(animal)}</strong></p>
      <form onSubmit={handleSubmit}>
        <fieldset disabled={isSubmitting || disabled || !businessToday}>
          <div className="breeding-form__field">
            <label htmlFor="breeding-type">Tipo de reproducción</label>
            <select id="breeding-type" {...fieldErrorAttributes(fieldErrors, 'breeding_type_id', 'breeding-type')} value={typeId} onChange={(event) => setTypeId(event.target.value)} required>
              <option value="">Selecciona un tipo</option>
              {types.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
            </select>
            <FieldError errors={fieldErrors} field="breeding_type_id" controlId="breeding-type" />
            {types.length === 0 && <p>No hay tipos de reproducción disponibles.</p>}
          </div>
          <div className="breeding-form__field">
            <label htmlFor="breeding-male">Macho (opcional)</label>
            <select id="breeding-male" {...fieldErrorAttributes(fieldErrors, 'male_id', 'breeding-male')} value={maleId} onChange={(event) => setMaleId(event.target.value)}>
              <option value="">Sin macho</option>
              {males.map((male) => <option key={male.id} value={male.id}>{animalLabel(male)}</option>)}
            </select>
            <FieldError errors={fieldErrors} field="male_id" controlId="breeding-male" />
            {males.length === 0 && <p>No hay machos disponibles. Puedes guardar sin macho.</p>}
          </div>
          <div className="breeding-form__field">
            <label htmlFor="breeding-date">Fecha</label>
            <input id="breeding-date" {...fieldErrorAttributes(fieldErrors, 'date', 'breeding-date')} type="date" value={date} max={businessToday ?? undefined}
              onChange={(event) => setDate(event.target.value)} required />
            <FieldError errors={fieldErrors} field="date" controlId="breeding-date" />
          </div>
          <div className="breeding-form__field">
            <label htmlFor="breeding-expected-birth">Fecha estimada de parto (opcional)</label>
            <input id="breeding-expected-birth" {...fieldErrorAttributes(fieldErrors, 'expected_birth', 'breeding-expected-birth')} type="date" value={expectedBirth}
              onChange={(event) => setExpectedBirth(event.target.value)} />
            <FieldError errors={fieldErrors} field="expected_birth" controlId="breeding-expected-birth" />
          </div>
          <div className="breeding-form__field">
            <label htmlFor="breeding-technician">Técnico (opcional)</label>
            <input id="breeding-technician" {...fieldErrorAttributes(fieldErrors, 'technician', 'breeding-technician')} maxLength={150} value={technician} onChange={(event) => setTechnician(event.target.value)} />
            <FieldError errors={fieldErrors} field="technician" controlId="breeding-technician" />
          </div>
          <div className="breeding-form__field breeding-form__wide">
            <label htmlFor="breeding-notes">Notas (opcional)</label>
            <textarea id="breeding-notes" {...fieldErrorAttributes(fieldErrors, 'notes', 'breeding-notes')} rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} />
            <FieldError errors={fieldErrors} field="notes" controlId="breeding-notes" />
          </div>
          <button type="submit">{isSubmitting ? 'Guardando...' : 'Guardar evento reproductivo'}</button>
        </fieldset>
      </form>
      {error && <p role="alert">{error}</p>}
    </section>
  )
}

export default BreedingForm
