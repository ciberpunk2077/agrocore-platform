import { type FormEvent, useEffect, useId, useRef, useState } from 'react'
import { getSession } from '../../auth/session'
import FieldError from '../../components/FieldError'
import { ApiError } from '../../lib/api'
import { fieldErrorAttributes, normalizeApiError } from '../../lib/api-errors'
import { createProduction, getProductionTypes, updateProduction } from '../production.service'
import type { ProductionRecord, ProductionType } from '../types'
import './ProductionForm.css'

type Catalog = { status: 'loading' } | { status: 'error'; message: string } | { status: 'data'; types: ProductionType[] }

// Decimal(12, 3) reserves nine integer digits. Never parse the quantity as Number.
function validQuantity(value: string): boolean {
  if (!/^\d+(?:\.\d{1,3})?$/.test(value)) return false
  const integer = value.split('.')[0].replace(/^0+/, '')
  return integer.length <= 9 && /[1-9]/.test(value)
}

// No user/org timezone is exposed by the frontend. Interpret wall time in the
// browser's local zone, using the offset at this date (including DST).
// Reject DST gaps/invalid dates; repeated DST times use Date's earlier instant.
function localTimestamp(date: string, time: string): { iso: string; instant: Date } | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) return null
  const [year, month, day] = date.split('-').map(Number)
  const [hour, minute] = time.split(':').map(Number)
  if (year < 1) return null
  const instant = new Date(`${date}T${time}:00`)
  if (!Number.isFinite(instant.getTime()) || instant.getFullYear() !== year || instant.getMonth() !== month - 1 ||
    instant.getDate() !== day || instant.getHours() !== hour || instant.getMinutes() !== minute) return null
  const offset = -instant.getTimezoneOffset()
  const absolute = Math.abs(offset)
  const suffix = `${offset >= 0 ? '+' : '-'}${String(Math.floor(absolute / 60)).padStart(2, '0')}:${String(absolute % 60).padStart(2, '0')}`
  return { iso: `${date}T${time}:00${suffix}`, instant }
}

function localFields(timestamp?: string): { date: string; time: string } {
  const instant = timestamp ? new Date(timestamp) : null
  if (!instant || !Number.isFinite(instant.getTime())) return { date: '', time: '' }
  const pad = (value: number) => String(value).padStart(2, '0')
  return { date: `${String(instant.getFullYear()).padStart(4, '0')}-${pad(instant.getMonth() + 1)}-${pad(instant.getDate())}`,
    time: `${pad(instant.getHours())}:${pad(instant.getMinutes())}` }
}

function submittedTimestamp(date: string, time: string, original?: string) {
  const initial = localFields(original)
  // Keep the exact wire value, including seconds/fractions and its offset.
  if (original && date === initial.date && time === initial.time) {
    return { iso: original, instant: new Date(original) }
  }
  return localTimestamp(date, time)
}

function ProductionForm({ animalId, onSaved, record, onCancel, onRecheck }: {
  animalId: string; onSaved: () => void; record?: ProductionRecord; onCancel?: () => void; onRecheck?: () => void
}) {
  const initial = localFields(record?.recorded_at)
  const prefix = useId()
  const ids = { type: `${prefix}-type`, date: `${prefix}-date`, time: `${prefix}-time`, quantity: `${prefix}-quantity`, notes: `${prefix}-notes` }
  const [catalog, setCatalog] = useState<Catalog>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [typeId, setTypeId] = useState(record?.production_type_id ?? '')
  const [date, setDate] = useState(initial.date)
  const [time, setTime] = useState(initial.time)
  const [quantity, setQuantity] = useState(record?.quantity ?? '')
  const [notes, setNotes] = useState(record?.notes ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const [success, setSuccess] = useState(false)
  const [uncertainResult, setUncertainResult] = useState(false)
  const busy = useRef(false)
  const lifetime = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    lifetime.current = controller
    return () => { controller.abort(); lifetime.current = null }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      const session = getSession()
      if (!session) { setCatalog({ status: 'error', message: 'No hay una sesión activa.' }); return }
      try {
        const types = await getProductionTypes(session.access, controller.signal)
        if (!controller.signal.aborted) setCatalog({ status: 'data', types })
      } catch (cause) {
        if (!controller.signal.aborted) setCatalog({ status: 'error', message: normalizeApiError(cause, 'No fue posible cargar los tipos de producción.').message })
      }
    }
    void load()
    return () => controller.abort()
  }, [attempt])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const controller = lifetime.current
    if (busy.current || !controller || controller.signal.aborted || catalog.status !== 'data') return
    setError(null)
    setSuccess(false)
    setUncertainResult(false)
    const errors: Record<string, string[]> = {}
    if (record && (record.animal_id !== animalId || !record.is_active)) {
      setError('El registro no está disponible para editar en este animal.')
      return
    }
    if (!catalog.types.some((type) => type.id === typeId)) errors.production_type_id = ['Selecciona un tipo de producción disponible.']
    if (!validQuantity(quantity)) errors.quantity = ['Introduce una cantidad mayor que cero, con hasta 9 dígitos enteros y 3 decimales (máximo 999999999.999).']
    const timestamp = submittedTimestamp(date, time, record?.recorded_at)
    if (!timestamp || !Number.isFinite(timestamp.instant.getTime())) errors.recorded_at = ['Introduce una fecha y hora local válidas.']
    else if (timestamp.instant.getTime() > Date.now()) errors.recorded_at = ['La fecha y hora no pueden ser futuras.']
    setFieldErrors(errors)
    if (Object.keys(errors).length || !timestamp) { setError('Revisa los campos del formulario.'); return }
    const session = getSession()
    if (!session) { setError('No hay una sesión activa.'); return }
    busy.current = true
    setSaving(true)
    try {
      const payload = { animal_id: animalId, production_type_id: typeId,
        recorded_at: timestamp.iso, quantity, notes }
      if (record) await updateProduction(record.id, payload, session.access, controller.signal)
      else await createProduction(payload, session.access, controller.signal)
      if (controller.signal.aborted) return
      setTypeId(''); setDate(''); setTime(''); setQuantity(''); setNotes('')
      setFieldErrors({})
      setSuccess(true)
      onSaved()
    } catch (cause) {
      if (controller.signal.aborted) return
      const uncertain = !(cause instanceof ApiError) || cause.status >= 500
      setUncertainResult(uncertain)
      const normalized = normalizeApiError(cause, cause instanceof ApiError && cause.status === 404
        ? 'El recurso no está disponible o no fue encontrado.' : record ? 'No fue posible actualizar la producción.' : 'No fue posible registrar la producción.')
      setError(uncertain
        ? record ? 'No se pudo confirmar el resultado de la actualización. Vuelve a consultar el historial antes de guardar nuevamente.'
          : 'No se pudo confirmar el resultado del registro. Revisa el historial con «Reintentar consulta» antes de intentar guardar nuevamente.'
        : normalized.message)
      setFieldErrors(normalized.fieldErrors)
    } finally {
      busy.current = false
      if (!controller.signal.aborted) setSaving(false)
    }
  }

  const types = catalog.status === 'data' ? catalog.types : []
  const selected = types.find((type) => type.id === typeId)
  return <div className="production-form">
    <h3>{record ? 'Editar producción' : 'Registrar producción'}</h3>
    <p>Fecha y hora en la zona local del navegador: {Intl.DateTimeFormat().resolvedOptions().timeZone}. El historial muestra UTC.</p>
    {catalog.status === 'loading' && <p role="status">Cargando tipos de producción...</p>}
    {catalog.status === 'error' && <div><p role="alert">{catalog.message}</p><button type="button" disabled={saving} onClick={() => {
      setCatalog({ status: 'loading' }); setAttempt((value) => value + 1)
    }}>Reintentar catálogo</button></div>}
    {catalog.status === 'data' && types.length === 0 && <p>No hay tipos de producción disponibles. No es posible guardar.</p>}
    {record && catalog.status === 'data' && !types.some((type) => type.id === record.production_type_id) &&
      <p>El tipo original ya no está disponible. Selecciona un tipo activo para guardar.</p>}
    {record && <p>Unidad almacenada: {record.unit}. Al guardar se aplicará la unidad vigente del tipo seleccionado: {selected?.default_unit ?? 'selecciona un tipo activo'}. La cantidad no se convierte automáticamente.</p>}
    <form onSubmit={submit}>
      <fieldset disabled={saving || catalog.status !== 'data' || types.length === 0}>
        <label htmlFor={ids.type}>Tipo de producción</label>
        <select id={ids.type} value={typeId} onChange={(event) => setTypeId(event.target.value)} required
          {...fieldErrorAttributes(fieldErrors, 'production_type_id', ids.type)}>
          <option value="">Selecciona un tipo</option>
          {record && !selected && typeId === record.production_type_id && <option value={record.production_type_id} disabled>Tipo original no disponible</option>}
          {types.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
        </select>
        <FieldError errors={fieldErrors} field="production_type_id" controlId={ids.type} />
        <p>Unidad: <output aria-live="polite">{selected?.default_unit ?? 'Selecciona un tipo de producción'}</output></p>
        <label htmlFor={ids.date}>Fecha</label>
        <input id={ids.date} type="date" required value={date} onChange={(event) => setDate(event.target.value)}
          {...fieldErrorAttributes(fieldErrors, 'recorded_at', ids.date)} />
        <FieldError errors={fieldErrors} field="recorded_at" controlId={ids.date} />
        <label htmlFor={ids.time}>Hora</label>
        <input id={ids.time} type="time" step="60" required value={time} onChange={(event) => setTime(event.target.value)}
          aria-invalid={fieldErrors.recorded_at?.length ? true : undefined}
          aria-describedby={fieldErrors.recorded_at?.length ? `${ids.date}-api-error` : undefined} />
        <label htmlFor={ids.quantity}>Cantidad</label>
        <input id={ids.quantity} type="text" inputMode="decimal" required value={quantity} onChange={(event) => setQuantity(event.target.value)}
          {...fieldErrorAttributes(fieldErrors, 'quantity', ids.quantity)} />
        <FieldError errors={fieldErrors} field="quantity" controlId={ids.quantity} />
        <label htmlFor={ids.notes}>Notas (opcional)</label>
        <textarea id={ids.notes} rows={3} value={notes} onChange={(event) => setNotes(event.target.value)}
          {...fieldErrorAttributes(fieldErrors, 'notes', ids.notes)} />
        <FieldError errors={fieldErrors} field="notes" controlId={ids.notes} />
        <button type="submit">{saving ? 'Guardando...' : record ? 'Guardar cambios' : 'Guardar producción'}</button>
      </fieldset>
      {record && <button type="button" disabled={saving} onClick={onCancel}>Cancelar</button>}
    </form>
    {error && <p role="alert">{error}</p>}
    {record && uncertainResult && <button type="button" disabled={saving} onClick={onRecheck}>Consultar historial y cerrar edición</button>}
    {success && <p role="status">Producción registrada correctamente.</p>}
  </div>
}

export default ProductionForm
