import { type FormEvent, useEffect, useId, useRef, useState } from 'react'
import { getSession, getSessionRevision } from '../../auth/session'
import FieldError from '../../components/FieldError'
import { ApiError } from '../../lib/api'
import { fieldErrorAttributes, normalizeApiError } from '../../lib/api-errors'
import { updateWeight } from '../weights.service'
import type { Weight, WeighingMethod } from '../types'
import './WeightForm.css'

// Decimal(6, 2): four integer digits, two decimal places. Keep the wire value as text.
function validWeight(value: string): boolean {
  return /^\d+(?:\.\d{1,2})?$/.test(value)
    && value.split('.')[0].replace(/^0+/, '').length <= 4 && /[1-9]/.test(value)
}

function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) return false
  const instant = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(instant.getTime()) && instant.toISOString().slice(0, 10) === value
}

function WeightEditForm({ record, animalId, birthDate, methods, catalogError, onCancel, onSaved, onRecheck }: {
  record: Weight; animalId: string; birthDate: string | null; methods: WeighingMethod[]
  catalogError: string | null; onCancel: () => void; onSaved: () => void; onRecheck: () => void
}) {
  const prefix = useId()
  const [date, setDate] = useState(record.date)
  const [weight, setWeight] = useState(record.weight)
  const [methodId, setMethodId] = useState(record.weighing_method_id)
  const [notes, setNotes] = useState<string | null>(record.notes)
  const [saving, setSaving] = useState(false)
  const [blocked, setBlocked] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const busy = useRef(false)
  const lifetime = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    lifetime.current = controller
    return () => { controller.abort(); lifetime.current = null }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const controller = lifetime.current
    if (busy.current || blocked || !controller || controller.signal.aborted || catalogError) return
    const errors: Record<string, string[]> = {}
    if (!validWeight(weight)) errors.weight = ['Introduce un peso positivo con hasta 4 dígitos enteros y 2 decimales (máximo 9999.99 kg).']
    // Backend timezone.localdate() uses UTC. The payload remains a plain date.
    if (!validDate(date)) errors.date = ['Introduce una fecha válida (AAAA-MM-DD).']
    else if (date > new Date().toISOString().slice(0, 10)) errors.date = ['La fecha del pesaje no puede ser futura.']
    else if (birthDate && date < birthDate) errors.date = ['La fecha del pesaje no puede ser anterior al nacimiento del animal.']
    if (!methods.some((method) => method.id === methodId)) errors.weighing_method_id = ['Selecciona un método activo.']
    setFieldErrors(errors)
    setError(null)
    if (Object.keys(errors).length) { setError('Revisa los campos del formulario.'); return }
    if (record.animal_id !== animalId) { setBlocked(true); setError('El pesaje no está disponible para este animal.'); return }
    const session = getSession()
    if (!session) { setError('No hay una sesión activa.'); return }
    const revision = getSessionRevision()
    busy.current = true
    setSaving(true)
    try {
      await updateWeight(record.id, { animal_id: animalId, weighing_method_id: methodId, date, weight, notes }, session.access, controller.signal)
      if (!controller.signal.aborted && revision === getSessionRevision()) onSaved()
    } catch (cause) {
      if (controller.signal.aborted || revision !== getSessionRevision()) return
      const status = cause instanceof ApiError ? cause.status : null
      const uncertain = status === null || status >= 500
      setBlocked(uncertain || status === 404 || status === 403 || status === 401)
      const normalized = normalizeApiError(cause, status === 404 ? 'El pesaje ya no está disponible o no fue encontrado.'
        : status === 401 ? 'La sesión ya no está disponible. Inicia sesión de nuevo.' : 'No fue posible actualizar el pesaje.')
      setError(uncertain ? 'No se pudo confirmar el resultado de la actualización. Consulta el historial antes de volver a guardar.' : normalized.message)
      setFieldErrors(normalized.fieldErrors)
    } finally {
      busy.current = false
      if (!controller.signal.aborted && revision === getSessionRevision()) setSaving(false)
    }
  }

  const available = methods.some((method) => method.id === methodId)
  return <div className="weight-form">
    <p>Pesaje: {record.id}. Animal: {animalId}.</p>
    {catalogError ? <p role="alert">El catálogo de métodos no pudo cargarse. No es posible guardar.</p>
      : !available && <p>El método seleccionado ya no está disponible. Selecciona un método activo para guardar.</p>}
    <form onSubmit={submit}>
      <fieldset disabled={saving || blocked || Boolean(catalogError) || methods.length === 0}>
        <div className="weight-form__field"><label htmlFor={`${prefix}-date`}>Fecha</label>
          <input id={`${prefix}-date`} type="date" value={date} required min={birthDate ?? undefined}
            onChange={(event) => setDate(event.target.value)} {...fieldErrorAttributes(fieldErrors, 'date', `${prefix}-date`)} />
          <FieldError errors={fieldErrors} field="date" controlId={`${prefix}-date`} /></div>
        <div className="weight-form__field"><label htmlFor={`${prefix}-weight`}>Peso (kg)</label>
          <input id={`${prefix}-weight`} type="text" inputMode="decimal" value={weight} required
            onChange={(event) => setWeight(event.target.value)} {...fieldErrorAttributes(fieldErrors, 'weight', `${prefix}-weight`)} />
          <FieldError errors={fieldErrors} field="weight" controlId={`${prefix}-weight`} /></div>
        <div className="weight-form__field"><label htmlFor={`${prefix}-method`}>Método de pesaje</label>
          <select id={`${prefix}-method`} value={methodId} required onChange={(event) => setMethodId(event.target.value)}
            {...fieldErrorAttributes(fieldErrors, 'weighing_method_id', `${prefix}-method`)}>
            <option value="">Selecciona un método</option>
            {!available && methodId && <option value={methodId} disabled>Método no disponible</option>}
            {methods.map((method) => <option key={method.id} value={method.id}>{method.name}</option>)}
          </select><FieldError errors={fieldErrors} field="weighing_method_id" controlId={`${prefix}-method`} /></div>
        <div className="weight-form__field weight-form__notes"><label htmlFor={`${prefix}-notes`}>Notas (opcional)</label>
          <textarea id={`${prefix}-notes`} rows={3} value={notes ?? ''} onChange={(event) => setNotes(event.target.value)}
            {...fieldErrorAttributes(fieldErrors, 'notes', `${prefix}-notes`)} />
          <FieldError errors={fieldErrors} field="notes" controlId={`${prefix}-notes`} /></div>
        <button type="submit">{saving ? 'Guardando...' : 'Guardar cambios'}</button>
      </fieldset>
      <button type="button" disabled={saving} onClick={() => { if (!busy.current) onCancel() }}>Cancelar</button>
    </form>
    {saving && <p role="status">Guardando cambios...</p>}
    {error && <p role="alert">{error}</p>}
    {blocked && <button type="button" disabled={saving} onClick={onRecheck}>Consultar historial y cerrar edición</button>}
  </div>
}

export default WeightEditForm
