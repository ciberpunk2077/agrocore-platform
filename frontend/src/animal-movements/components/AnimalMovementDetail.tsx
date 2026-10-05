import { useEffect, useState } from 'react'
import type { Animal, Farm, Lot } from '../../animals/types'
import { getSession, getSessionRevision } from '../../auth/session'
import { ApiError } from '../../lib/api'
import { normalizeApiError } from '../../lib/api-errors'
import { getAnimalMovement } from '../animal-movements.service'
import type { AnimalMovement, MovementType } from '../types'

interface Props {
  movementId: string; animalId: string; revision: number; organizationId: string
  types: MovementType[]; farms: Farm[]; lots: Lot[]; animal: Animal; onClose: () => void
}
export default function AnimalMovementDetail({ movementId, animalId, revision, organizationId, types, farms, lots, animal, onClose }: Props) {
  const [record, setRecord] = useState<AnimalMovement | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    const current = () => !controller.signal.aborted && revision === getSessionRevision()
    async function load() {
      setRecord(null); setError(null); setLoading(true)
      const session = getSession()
      if (!session || !current()) { if (current()) { setError('No hay una sesión activa.'); setLoading(false) }; return }
      try {
        const result = await getAnimalMovement(movementId, animalId, session.access, controller.signal)
        if (current()) setRecord(result)
      } catch (cause) {
        if (current()) setError(cause instanceof ApiError && cause.status === 404 ? 'Este movimiento ya no está disponible.' : normalizeApiError(cause, 'No fue posible consultar el movimiento.').message)
      } finally { if (current()) setLoading(false) }
    }
    void load()
    return () => controller.abort()
  }, [movementId, animalId, revision, organizationId, retry])
  const name = (id: string | null, options: { id: string; name: string }[]) => id === null ? 'Sin registro' : options.find(o => o.id === id)?.name ?? id
  return <section aria-label="Detalle del movimiento">
    <h3>Detalle del movimiento</h3>
    {loading && <p role="status">Cargando detalle...</p>}
    {error && <div><p role="alert">{error}</p><button type="button" onClick={() => setRetry(v => v + 1)}>Reintentar detalle</button></div>}
    {record && <dl>
      <dt>ID</dt><dd>{record.id}</dd><dt>Fecha</dt><dd>{record.date}</dd>
      <dt>Tipo</dt><dd>{name(record.movement_type_id, types)}</dd>
      <dt>Finca origen</dt><dd>{name(record.origin_farm_id, farms)}</dd><dt>Lote origen</dt><dd>{name(record.origin_lot_id, lots)}</dd>
      <dt>Finca destino</dt><dd>{name(record.destination_farm_id, farms)}</dd><dt>Lote destino</dt><dd>{name(record.destination_lot_id, lots)}</dd>
      <dt>Motivo</dt><dd style={{ whiteSpace: 'pre-wrap' }}>{record.reason ?? 'Sin motivo'}</dd>
      <dt>Notas</dt><dd style={{ whiteSpace: 'pre-wrap' }}>{record.notes ?? 'Sin notas'}</dd>
      <dt>Status anterior (snapshot)</dt><dd>{record.origin_status_id === null ? 'Sin snapshot' : record.origin_status_id === animal.status_id ? `${animal.status} (${record.origin_status_id})` : record.origin_status_id}</dd>
    </dl>}
    <button type="button" onClick={onClose}>Volver</button>
  </section>
}
