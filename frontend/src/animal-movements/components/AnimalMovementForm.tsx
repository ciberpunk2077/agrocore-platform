import FieldError from '../../components/FieldError'
import { fieldErrorAttributes, normalizeApiError } from '../../lib/api-errors'
import { type FormEvent, useEffect, useRef, useState } from 'react'

import type { Animal, Farm, Lot } from '../../animals/types'
import { validDate } from '../validation'
import type { AnimalMovementCreatePayload, MovementType } from '../types'
import './AnimalMovementForm.css'

interface AnimalMovementFormProps {
  animalId: string
  animal: Animal
  types: MovementType[]
  farms: Farm[]
  lots: Lot[]
  lastDate: string
  disabled: boolean
  onCreate: (payload: AnimalMovementCreatePayload) => Promise<void>
}

function AnimalMovementForm({
  animalId, animal, types, farms, lots, lastDate, disabled, onCreate,
}: AnimalMovementFormProps) {
  const [date, setDate] = useState('')
  const [typeId, setTypeId] = useState('')
  const [destinationFarmId, setDestinationFarmId] = useState('')
  const [destinationLotId, setDestinationLotId] = useState('')
  const [reason, setReason] = useState('')
  const [notes, setNotes] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const submitting = useRef(false)
  const mounted = useRef(false)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  // Match timezone.localdate(): backend settings use TIME_ZONE = UTC, USE_TZ = True.
  const [today, setToday] = useState(() => new Date().toISOString().slice(0, 10))

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>

    function scheduleMidnight() {
      const now = new Date()
      const nextMidnight = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1)
      timer = setTimeout(syncToday, nextMidnight - now.getTime())
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
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('focus', syncToday)
    }
  }, [])

  const code = types.find((item) => item.id === typeId)?.code
  const needsOrigin = code === 'TRANSFER' || code === 'EXIT' || code === 'SALE'
  const isEntry = code === 'ENTRY' || code === 'PURCHASE'
  const forbidsDestination = code === 'EXIT' || code === 'SALE'
  const needsDestination = code === 'TRANSFER' || isEntry
  const hasLocation = Boolean(animal.farm_id || animal.lot_id)
  const originFarm = farms.find((item) => item.id === animal.farm_id)
  const originLot = lots.find((item) => item.id === animal.lot_id && item.farm_id === originFarm?.id)
  const destinationLots = lots.filter((item) => item.farm_id === destinationFarmId)
  const minimumDate = lastDate
    ? new Date(Date.parse(`${lastDate}T00:00:00Z`) + 86400000).toISOString().slice(0, 10)
    : undefined
  const noDateAvailable = Boolean(minimumDate && minimumDate > today)
  const unavailableOrigin = needsOrigin && (!originFarm || !originLot)
  const blocked = disabled || !animal.is_active || noDateAvailable || unavailableOrigin || (isEntry && hasLocation)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFieldErrors({})
    if (submitting.current || blocked || animal.id !== animalId) return
    setError(null)
    if (!validDate(date) || !types.some(item => item.id === typeId)) {
      setError('Completa la fecha y el tipo de movimiento.')
      return
    }
    if (date > today) {
      setError('La fecha del movimiento no puede ser futura.')
      return
    }
    if (lastDate && date <= lastDate) {
      setError('La fecha del movimiento debe ser posterior al último movimiento registrado.')
      return
    }
    if (!forbidsDestination && (
      (needsDestination && !destinationFarmId) ||
      (destinationFarmId && (!farms.some(item => item.id === destinationFarmId) || !destinationLots.some((item) => item.id === destinationLotId)))
    )) {
      setError('Selecciona una finca y un lote de destino válidos.')
      return
    }
    if (code === 'TRANSFER' && destinationFarmId === originFarm?.id && destinationLotId === originLot?.id) {
      setError('El origen y el destino de un traslado no pueden ser iguales.')
      return
    }
    if (reason.trim().length > 255) { setError('El motivo admite hasta 255 caracteres.'); return }
    submitting.current = true
    setIsSubmitting(true)
    try {
      await onCreate({
        animal_id: animalId,
        movement_type_id: typeId,
        date,
        origin_farm_id: needsOrigin ? originFarm!.id : null,
        origin_lot_id: needsOrigin ? originLot!.id : null,
        destination_farm_id: forbidsDestination ? null : destinationFarmId || null,
        destination_lot_id: forbidsDestination ? null : destinationLotId || null,
        reason: reason.trim(),
        notes: notes.trim(),
      })
    } catch (cause) {
      if (mounted.current) {
        const normalized = normalizeApiError(cause, 'No fue posible registrar el movimiento. Revisa los datos e intenta de nuevo.')
        setError(normalized.message)
        setFieldErrors(normalized.fieldErrors)
      }
    } finally {
      submitting.current = false
      if (mounted.current) setIsSubmitting(false)
    }
  }

  return (
    <section className="movement-form">
      <h3>Registrar movimiento</h3>
      {!animal.is_active && <p role="alert">No es posible registrar movimientos para un animal inactivo.</p>}
      {noDateAvailable && <p role="status">Ya existe un movimiento con fecha de hoy o posterior. No hay una fecha válida disponible para otro movimiento.</p>}
      {types.length === 0 && <p role="status">No hay tipos de movimiento disponibles.</p>}
      <form onSubmit={handleSubmit}>
        <fieldset disabled={disabled || isSubmitting || !animal.is_active || noDateAvailable || types.length === 0}>
          <div className="movement-form__field">
            <label htmlFor="movement-date">Fecha</label>
            <input id="movement-date" {...fieldErrorAttributes(fieldErrors, 'date', 'movement-date')} type="date" value={date} min={minimumDate} max={today}
              onChange={(event) => setDate(event.target.value)} required />
            <FieldError errors={fieldErrors} field="date" controlId="movement-date" />
          </div>
          <div className="movement-form__field">
            <label htmlFor="movement-type">Tipo de movimiento</label>
            <select id="movement-type" {...fieldErrorAttributes(fieldErrors, 'movement_type_id', 'movement-type')} value={typeId} required onChange={(event) => {
              setTypeId(event.target.value)
              setDestinationFarmId('')
              setDestinationLotId('')
            }}>
              <option value="">Selecciona un tipo</option>
              {types.map((item) => (
                <option key={item.id} value={item.id}
                  disabled={hasLocation && (item.code === 'ENTRY' || item.code === 'PURCHASE')}>
                  {item.name}
                </option>
              ))}
            </select>
            <FieldError errors={fieldErrors} field="movement_type_id" controlId="movement-type" />
          </div>
          {hasLocation && <p className="movement-form__wide">Entrada y compra requieren un animal sin ubicación actual.</p>}
          {needsOrigin && (
            <>
              <div className="movement-form__field">
                <label htmlFor="movement-origin-farm">Finca origen</label>
                <select id="movement-origin-farm" {...fieldErrorAttributes(fieldErrors, 'origin_farm_id', 'movement-origin-farm')} value={originFarm?.id ?? ''} disabled>
                  <option value="">Sin finca activa disponible</option>
                  {originFarm && <option value={originFarm.id}>{originFarm.name}</option>}
                </select>
                <FieldError errors={fieldErrors} field="origin_farm_id" controlId="movement-origin-farm" />
              </div>
              <div className="movement-form__field">
                <label htmlFor="movement-origin-lot">Lote origen</label>
                <select id="movement-origin-lot" {...fieldErrorAttributes(fieldErrors, 'origin_lot_id', 'movement-origin-lot')} value={originLot?.id ?? ''} disabled>
                  <option value="">Sin lote activo disponible</option>
                  {originLot && <option value={originLot.id}>{originLot.name}</option>}
                </select>
                <FieldError errors={fieldErrors} field="origin_lot_id" controlId="movement-origin-lot" />
              </div>
              <p className="movement-form__wide">El origen corresponde a la ubicación actual del animal.</p>
              {unavailableOrigin && <p className="movement-form__wide" role="alert">Este movimiento requiere una finca y un lote de origen activos disponibles.</p>}
            </>
          )}
          {typeId && !forbidsDestination && (
            <>
              <div className="movement-form__field">
                <label htmlFor="movement-destination-farm">Finca destino</label>
                <select id="movement-destination-farm" {...fieldErrorAttributes(fieldErrors, 'destination_farm_id', 'movement-destination-farm')} value={destinationFarmId} required={needsDestination}
                  onChange={(event) => {
                    setDestinationFarmId(event.target.value)
                    setDestinationLotId('')
                  }}>
                  <option value="">Selecciona una finca</option>
                  {farms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
                <FieldError errors={fieldErrors} field="destination_farm_id" controlId="movement-destination-farm" />
              </div>
              <div className="movement-form__field">
                <label htmlFor="movement-destination-lot">Lote destino</label>
                <select id="movement-destination-lot" {...fieldErrorAttributes(fieldErrors, 'destination_lot_id', 'movement-destination-lot')} value={destinationLotId} required={Boolean(destinationFarmId)}
                  disabled={!destinationFarmId} onChange={(event) => setDestinationLotId(event.target.value)}>
                  <option value="">Selecciona un lote</option>
                  {destinationLots.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select>
                <FieldError errors={fieldErrors} field="destination_lot_id" controlId="movement-destination-lot" />
              </div>
            </>
          )}
          <div className="movement-form__field movement-form__wide">
            <label htmlFor="movement-reason">Motivo (opcional)</label>
            <input id="movement-reason" {...fieldErrorAttributes(fieldErrors, 'reason', 'movement-reason')} value={reason} maxLength={255} onChange={(event) => setReason(event.target.value)} />
            <FieldError errors={fieldErrors} field="reason" controlId="movement-reason" />
          </div>
          <div className="movement-form__field movement-form__wide">
            <label htmlFor="movement-notes">Notas (opcional)</label>
            <textarea id="movement-notes" {...fieldErrorAttributes(fieldErrors, 'notes', 'movement-notes')} value={notes} rows={3} onChange={(event) => setNotes(event.target.value)} />
            <FieldError errors={fieldErrors} field="notes" controlId="movement-notes" />
          </div>
          <button type="submit" disabled={blocked}>{isSubmitting ? 'Guardando...' : 'Guardar movimiento'}</button>
        </fieldset>
      </form>
      {error && <p role="alert">{error}</p>}
    </section>
  )
}

export default AnimalMovementForm
