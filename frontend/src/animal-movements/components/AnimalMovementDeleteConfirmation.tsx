import { useEffect, useRef, useState } from 'react'
import type { Farm, Lot } from '../../animals/types'
import { getSession, getSessionRevision } from '../../auth/session'
import { normalizeApiError } from '../../lib/api-errors'
import { getAnimalMovement, getAnimalMovementHistory, getMovementAnimal } from '../animal-movements.service'
import type { DeleteSnapshot } from '../create-protocol'
import type { MovementType } from '../types'

interface Props {
  movementId: string; animalId: string; revision: number; organizationId: string
  types: MovementType[]; farms: Farm[]; lots: Lot[]; disabled: boolean
  onCancel: () => void; onConfirm: (snapshot: DeleteSnapshot) => Promise<void>
}
export default function AnimalMovementDeleteConfirmation({ movementId, animalId, revision, organizationId, types, farms, lots, disabled, onCancel, onConfirm }: Props) {
  const [snapshot, setSnapshot] = useState<DeleteSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [pending, setPending] = useState(false)
  const busy = useRef(false)
  const latestSnapshot = useRef<DeleteSnapshot | null>(null)
  const mounted = useRef(false)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => {
    const c = new AbortController()
    const current = () => !c.signal.aborted && getSessionRevision() === revision
    async function prepare() {
      latestSnapshot.current = null
      setLoading(true); setSnapshot(null); setError(null)
      const session = getSession()
      if (!session || !current()) { if (current()) { setError('No hay una sesión activa.'); setLoading(false) }; return }
      try {
        const [movement, history, animal] = await Promise.all([
          getAnimalMovement(movementId, animalId, session.access, c.signal),
          getAnimalMovementHistory(animalId, session.access, c.signal),
          getMovementAnimal(animalId, session.access, c.signal).catch(() => { throw new Error('No puede eliminarse: no fue posible obtener un Animal activo fresco y válido.') }),
        ])
        if (!current()) return
        if (!animal.is_active) { setError('No puede eliminarse el movimiento de un Animal inactivo.'); return }
        if (history[0]?.id !== movementId) { setError('Solo puede eliminarse el último movimiento activo.'); return }
        const prepared = { revision, organizationId, movement, history, animal }
        latestSnapshot.current = prepared
        setSnapshot(prepared)
      } catch (cause) {
        if (current()) setError(cause instanceof Error && cause.message.startsWith('No puede eliminarse:') ? cause.message : normalizeApiError(cause, 'No fue posible preparar la eliminación. Consulta nuevamente antes de confirmar.').message)
      } finally { if (current()) setLoading(false); c.abort() }
    }
    void prepare()
    return () => { c.abort(); latestSnapshot.current = null }
  }, [movementId, animalId, revision, organizationId, retry])
  async function confirm() {
    if (busy.current || loading || disabled || !snapshot || snapshot !== latestSnapshot.current || revision !== getSessionRevision() || !mounted.current) return
    busy.current = true; setPending(true); setError(null)
    try { await onConfirm(snapshot) }
    catch (cause) { if (mounted.current && revision === getSessionRevision()) setError(normalizeApiError(cause, 'No fue posible eliminar el movimiento.').message) }
    finally { busy.current = false; if (mounted.current && revision === getSessionRevision()) setPending(false) }
  }
  const name = (id: string | null, options: { id: string; name: string }[]) => id === null ? 'Sin ubicación' : options.find(o => o.id === id)?.name ?? id
  return <section aria-label="Confirmar eliminación de movimiento">
    <h3>Eliminar movimiento</h3>
    {loading && <p role="status">Preparando confirmación...</p>}
    {snapshot && <>
      <dl>
        <dt>ID</dt><dd>{snapshot.movement.id}</dd><dt>Fecha</dt><dd>{snapshot.movement.date}</dd>
        <dt>Tipo</dt><dd>{name(snapshot.movement.movement_type_id, types)}</dd>
        <dt>Origen</dt><dd>{name(snapshot.movement.origin_farm_id, farms)} / {name(snapshot.movement.origin_lot_id, lots)}</dd>
        <dt>Destino</dt><dd>{name(snapshot.movement.destination_farm_id, farms)} / {name(snapshot.movement.destination_lot_id, lots)}</dd>
        <dt>Motivo</dt><dd style={{ whiteSpace: 'pre-wrap' }}>{snapshot.movement.reason ?? 'Sin motivo'}</dd>
        <dt>Notas</dt><dd style={{ whiteSpace: 'pre-wrap' }}>{snapshot.movement.notes ?? 'Sin notas'}</dd>
      </dl>
      <p>Se restaurará la ubicación histórica: finca {name(snapshot.movement.origin_farm_id, farms)}; lote {name(snapshot.movement.origin_lot_id, lots)}.</p>
      <p>{snapshot.movement.origin_status_id === null ? `Se conservará el status actual: ${snapshot.animal.status} (${snapshot.animal.status_id}).`
        : `Se restaurará el status histórico: ${snapshot.movement.origin_status_id === snapshot.animal.status_id ? snapshot.animal.status + ' ' : ''}${snapshot.movement.origin_status_id}.`}</p>
      <p>Esta restauración puede sobrescribir cambios independientes posteriores de ubicación y status. Se usa el origen original aunque el tipo haya cambiado. Las referencias históricas inactivas no se reparan ni sustituyen.</p>
      <p>El movimiento desaparecerá del historial activo mediante borrado lógico. No hay restauración desde esta interfaz.</p>
      <button type="button" disabled={disabled || pending || loading} onClick={() => void confirm()}>Confirmar eliminación</button>
    </>}
    {error && <div><p role="alert">{error}</p>{!snapshot && <button type="button" disabled={disabled || pending || loading} onClick={() => setRetry(v => v + 1)}>Reintentar preparación</button>}</div>}
    <button type="button" disabled={disabled || pending} onClick={() => { if (!busy.current && revision === getSessionRevision()) onCancel() }}>Cancelar eliminación</button>
  </section>
}
