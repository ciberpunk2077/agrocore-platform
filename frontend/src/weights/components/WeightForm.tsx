import { type FormEvent, useEffect, useState } from 'react'

import { getSession } from '../../auth/session'
import type { WeightCreatePayload, WeighingMethod } from '../types'
import { createWeight, getWeighingMethods } from '../weights.service'
import './WeightForm.css'

interface WeightFormProps {
  animalId: string
  onMethodsLoaded: (methods: WeighingMethod[]) => void
  onSaved: () => void
}

function WeightForm({ animalId, onMethodsLoaded, onSaved }: WeightFormProps) {
  const [methods, setMethods] = useState<WeighingMethod[]>([])
  const [date, setDate] = useState('')
  const [weight, setWeight] = useState('')
  const [methodId, setMethodId] = useState('')
  const [notes, setNotes] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    let isActive = true

    async function loadMethods() {
      const session = getSession()

      if (!session) {
        setError('No hay una sesión activa.')
        setIsLoading(false)
        return
      }

      try {
        const data = await getWeighingMethods(session.access)

        if (isActive) {
          setMethods(data)
          onMethodsLoaded(data)
        }
      } catch {
        if (isActive) {
          setError('No fue posible cargar los métodos de pesaje.')
        }
      } finally {
        if (isActive) {
          setIsLoading(false)
        }
      }
    }

    void loadMethods()

    return () => {
      isActive = false
    }
  }, [onMethodsLoaded])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (isLoading || isSubmitting) return

    setError(null)
    setSuccess(false)

    const numericWeight = Number(weight)

    if (!date || !weight.trim() || !methods.some((method) => method.id === methodId)) {
      setError('Completa la fecha, el peso y el método de pesaje.')
      return
    }

    if (!Number.isFinite(numericWeight) || numericWeight <= 0) {
      setError('El peso debe ser un número mayor que cero.')
      return
    }

    const session = getSession()

    if (!session) {
      setError('No hay una sesión activa.')
      return
    }

    const payload: WeightCreatePayload = {
      animal_id: animalId,
      weighing_method_id: methodId,
      date,
      weight: numericWeight,
      notes: notes.trim() || null,
    }

    setIsSubmitting(true)

    try {
      await createWeight(payload, session.access)
      setDate('')
      setWeight('')
      setMethodId('')
      setNotes('')
      setSuccess(true)
      onSaved()
    } catch {
      setError('No fue posible registrar el peso. Intenta de nuevo.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="weight-form">
      <h2>Registrar peso</h2>
      {isLoading ? (
        <p role="status">Cargando métodos de pesaje...</p>
      ) : (
        <form onSubmit={handleSubmit}>
          <fieldset disabled={isSubmitting || methods.length === 0}>
            <div className="weight-form__field">
              <label htmlFor="weight-date">Fecha</label>
              <input id="weight-date" type="date" value={date}
                onChange={(event) => setDate(event.target.value)} required />
            </div>
            <div className="weight-form__field">
              <label htmlFor="weight-value">Peso (kg)</label>
              <input id="weight-value" type="number" min="0" step="any" value={weight}
                onChange={(event) => setWeight(event.target.value)} required />
            </div>
            <div className="weight-form__field">
              <label htmlFor="weight-method">Método de pesaje</label>
              <select id="weight-method" value={methodId}
                onChange={(event) => setMethodId(event.target.value)} required>
                <option value="">Selecciona un método</option>
                {methods.map((method) => (
                  <option key={method.id} value={method.id}>{method.name}</option>
                ))}
              </select>
            </div>
            <div className="weight-form__field weight-form__notes">
              <label htmlFor="weight-notes">Notas (opcional)</label>
              <textarea id="weight-notes" value={notes} rows={3}
                onChange={(event) => setNotes(event.target.value)} />
            </div>
            <button type="submit">
              {isSubmitting ? 'Guardando...' : 'Guardar peso'}
            </button>
          </fieldset>
          {methods.length === 0 && !error && (
            <p>No hay métodos de pesaje disponibles.</p>
          )}
        </form>
      )}
      {error && <p className="weight-form__error" role="alert">{error}</p>}
      {success && <p className="weight-form__success" role="status">Peso registrado correctamente.</p>}
    </section>
  )
}

export default WeightForm
