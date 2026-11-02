import { useEffect, useState } from 'react'
import { recordDetail, dateLabel, textLabel } from '../../reproduction/RecordDetail'
import { useCallback } from 'react'
import './AnimalMovementDetail.css'
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
  const headingRef = useCallback((node: HTMLHeadingElement | null) => {
    if (!node) return
    node.focus({ preventScroll: true })
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? true
    node.scrollIntoView({ behavior: reducedMotion ? 'instant' : 'smooth', block: 'start' })
  }, [])
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
  const name = (id: string | null, options: { id: string; name: string }[]) =>
    id === null ? 'Sin datos' : options.find(option => option.id === id)?.name ?? 'Nombre no disponible · referencia registrada'
  const location = (farmId: string | null, lotId: string | null) => <span className="movement-detail__location">
    <span><span aria-hidden="true">⌂ </span>Finca<strong>{name(farmId, farms)}</strong></span>
    <span><span aria-hidden="true">▧ </span>Lote<strong>{name(lotId, lots)}</strong></span>
  </span>
  const technical = record && <details className="movement-detail__technical"><summary>Ver referencias técnicas</summary><dl>
    {Object.entries({ 'Movimiento': record.id, 'Tipo': record.movement_type_id,
      'Finca origen': record.origin_farm_id, 'Lote origen': record.origin_lot_id,
      'Finca destino': record.destination_farm_id, 'Lote destino': record.destination_lot_id,
      'Estado anterior': record.origin_status_id }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? 'Sin datos'}</dd></div>)}
  </dl></details>
  return recordDetail({ kind: 'movement', id: movementId, title: record ? `Movimiento · ${name(record.movement_type_id, types)}` : 'Detalle del movimiento', date: record?.date,
    loading: loading ? 'Cargando detalle...' : undefined, error: error ?? undefined,
    fields: record ? [
      { label: 'Fecha del movimiento', value: <time dateTime={record.date}>{dateLabel(record.date)}</time> },
      { label: 'Tipo de movimiento', value: name(record.movement_type_id, types) },
      { label: 'Origen', value: location(record.origin_farm_id, record.origin_lot_id) },
      { label: 'Destino', value: location(record.destination_farm_id, record.destination_lot_id) },
      { label: 'Motivo', value: textLabel(record.reason) },
      { label: 'Estado anterior (snapshot)', value: record.origin_status_id === null ? 'Sin snapshot' :
        record.origin_status_id === animal.status_id ? textLabel(animal.status) : 'Información no disponible · referencia registrada' },
      { label: 'Referencias del registro', value: technical },
    ] : [], notes: record?.notes, onClose, onRetry: () => setRetry(value => value + 1), headingRef,
  })
}
