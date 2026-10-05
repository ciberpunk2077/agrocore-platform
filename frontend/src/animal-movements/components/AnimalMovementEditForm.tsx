import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { Farm, Lot } from '../../animals/types'
import { getSession, getSessionRevision } from '../../auth/session'
import { normalizeApiError } from '../../lib/api-errors'
import { getAnimalMovement, getAnimalMovementHistory } from '../animal-movements.service'
import type { AnimalMovement, AnimalMovementUpdatePayload, MovementType } from '../types'
import { inactiveOrigin, updateError, updatePayload } from '../update-validation'

interface Props {
  movementId: string; animalId: string; revision: number; organizationId: string
  types: MovementType[]; farms: Farm[]; lots: Lot[]; disabled: boolean; animalActive: boolean
  onCancel: () => void; onSave: (record: AnimalMovement, payload: AnimalMovementUpdatePayload, history: AnimalMovement[]) => Promise<void>
}
export default function AnimalMovementEditForm({ movementId, animalId, revision, organizationId, types, farms, lots, disabled, animalActive, onCancel, onSave }: Props) {
  const [record, setRecord] = useState<AnimalMovement | null>(null)
  const [draft, setDraft] = useState<AnimalMovementUpdatePayload | null>(null)
  const [previousDate, setPreviousDate] = useState('')
  const [loading, setLoading] = useState(true)
  const [preparationError, setPreparationError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const busy = useRef(false)
  const mounted = useRef(false)
  const preparedHistory = useRef<AnimalMovement[]>([])
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => {
    const c = new AbortController()
    const current = () => !c.signal.aborted && revision === getSessionRevision()
    async function prepare() {
      setLoading(true); setRecord(null); setDraft(null); setPreparationError(null); setError(null)
      const session = getSession()
      if (!session || !current()) { if (current()) { setPreparationError('No hay una sesión activa.'); setLoading(false) }; return }
      try {
        const [fresh, history] = await Promise.all([
          getAnimalMovement(movementId, animalId, session.access, c.signal), getAnimalMovementHistory(animalId, session.access, c.signal),
        ])
        if (!current()) return
        if (history[0]?.id !== movementId) { setPreparationError('Solo puede editarse el último movimiento activo.'); return }
        if (inactiveOrigin(fresh, farms, lots)) { setPreparationError('El origen histórico no está disponible entre las relaciones activas. No puede sustituirse para editar.'); return }
        preparedHistory.current = history
        setRecord(fresh); setDraft(updatePayload(fresh)); setPreviousDate(history.find(m => m.id !== movementId)?.date ?? '')
      } catch (cause) { if (current()) setPreparationError(normalizeApiError(cause, 'No fue posible preparar la edición.').message) }
      finally { if (current()) setLoading(false) }
    }
    void prepare()
    return () => c.abort()
  }, [movementId, animalId, revision, organizationId, farms, lots, retry])
  function change<K extends keyof AnimalMovementUpdatePayload>(key: K, value: AnimalMovementUpdatePayload[K]) {
    setDraft(old => old ? { ...old, [key]: value } : old)
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy.current || disabled || !animalActive || !record || !draft || revision !== getSessionRevision()) return
    const invalid = updateError(draft, record, previousDate, types, farms, lots)
    if (invalid) { setError(invalid); return }
    busy.current = true; setSubmitting(true); setError(null)
    try { await onSave(record, { ...draft }, preparedHistory.current) }
    catch (cause) { if (mounted.current && revision === getSessionRevision()) setError(normalizeApiError(cause, 'No fue posible actualizar el movimiento.').message) }
    finally { busy.current = false; if (mounted.current && revision === getSessionRevision()) setSubmitting(false) }
  }
  const code = types.find(t => t.id === draft?.movement_type_id)?.code
  const withoutDestination = code === 'EXIT' || code === 'SALE'
  const min = previousDate ? new Date(Date.parse(`${previousDate}T00:00:00Z`) + 86400000).toISOString().slice(0, 10) : undefined
  return <section aria-label="Editar movimiento">
    <h3>Editar movimiento</h3>
    {loading && <p role="status">Preparando edición...</p>}
    {preparationError && <div><p role="alert">{preparationError}</p><button type="button" disabled={disabled} onClick={() => setRetry(v => v + 1)}>Reintentar preparación</button></div>}
    {!animalActive && <p role="alert">No puede actualizarse un movimiento de un animal inactivo.</p>}
    {record && draft && <form onSubmit={submit}>
      <p>Animal: {record.animal_id}</p><p>Origen histórico: {record.origin_farm_id ?? 'Sin finca'} / {record.origin_lot_id ?? 'Sin lote'}</p>
      <p>Status anterior: {record.origin_status_id ?? 'Sin snapshot'}</p>
      <fieldset disabled={disabled || submitting || !animalActive}>
        <label htmlFor="movement-edit-type">Tipo</label><select id="movement-edit-type" value={draft.movement_type_id} onChange={e => {
          const type = types.find(t => t.id === e.target.value)
          setDraft(old => old ? { ...old, movement_type_id: e.target.value, ...(type?.code === 'EXIT' || type?.code === 'SALE' ? { destination_farm_id: null, destination_lot_id: null } : {}) } : old)
        }}>
          {!types.some(t => t.id === draft.movement_type_id) && <option value={draft.movement_type_id}>Tipo histórico no activo ({draft.movement_type_id})</option>}
          {types.map(t => <option key={t.id} value={t.id} disabled={['TRANSFER','EXIT','SALE'].includes(t.code) && (!record.origin_farm_id || !record.origin_lot_id)}>{t.name}</option>)}
        </select>
        <label htmlFor="movement-edit-date">Fecha</label><input id="movement-edit-date" type="date" value={draft.date} min={min} max={new Date().toISOString().slice(0,10)} onChange={e => change('date',e.target.value)} required />
        {!withoutDestination && <>
          <label htmlFor="movement-edit-farm">Finca destino</label><select id="movement-edit-farm" value={draft.destination_farm_id ?? ''} onChange={e => setDraft(old => old ? { ...old, destination_farm_id: e.target.value || null, destination_lot_id: null } : old)}>
            <option value="">Sin finca</option>
            {draft.destination_farm_id && !farms.some(f => f.id === draft.destination_farm_id) && <option value={draft.destination_farm_id}>Finca histórica no activa ({draft.destination_farm_id})</option>}
            {farms.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          <label htmlFor="movement-edit-lot">Lote destino</label><select id="movement-edit-lot" value={draft.destination_lot_id ?? ''} onChange={e => change('destination_lot_id',e.target.value || null)} disabled={!draft.destination_farm_id}>
            <option value="">Sin lote</option>
            {draft.destination_lot_id && !lots.some(l => l.id === draft.destination_lot_id && l.farm_id === draft.destination_farm_id) && <option value={draft.destination_lot_id}>Lote histórico no activo ({draft.destination_lot_id})</option>}
            {lots.filter(l => l.farm_id === draft.destination_farm_id).map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </>}
        <label htmlFor="movement-edit-reason">Motivo</label><input id="movement-edit-reason" maxLength={255} value={draft.reason ?? ''} onChange={e => change('reason',e.target.value)} />
        <label htmlFor="movement-edit-notes">Notas</label><textarea id="movement-edit-notes" value={draft.notes ?? ''} onChange={e => change('notes',e.target.value)} />
        <button type="submit">{submitting ? 'Guardando...' : 'Guardar cambios'}</button>
      </fieldset>
    </form>}
    {error && <p role="alert">{error}</p>}
    <button type="button" disabled={disabled || submitting} onClick={onCancel}>Cancelar edición</button>
  </section>
}
