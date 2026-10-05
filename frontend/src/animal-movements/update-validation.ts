import type { Farm, Lot } from '../animals/types'
import type { AnimalMovement, AnimalMovementUpdatePayload, MovementType } from './types'
import { validDate } from './validation'

export function inactiveOrigin(record: AnimalMovement, farms: Farm[], lots: Lot[]): boolean {
  return (record.origin_farm_id !== null && !farms.some(f => f.id === record.origin_farm_id))
    || (record.origin_lot_id !== null && !lots.some(l => l.id === record.origin_lot_id && l.farm_id === record.origin_farm_id))
}
export function updateError(payload: AnimalMovementUpdatePayload, record: AnimalMovement, previousDate: string, types: MovementType[], farms: Farm[], lots: Lot[]): string | null {
  if (payload.animal_id !== record.animal_id || payload.origin_farm_id !== record.origin_farm_id || payload.origin_lot_id !== record.origin_lot_id) return 'El animal y el origen histórico son inmutables.'
  if (inactiveOrigin(record, farms, lots)) return 'El origen histórico no está disponible entre las relaciones activas. No puede sustituirse para editar.'
  if (!validDate(payload.date)) return 'Introduce una fecha válida.'
  if (payload.date > new Date().toISOString().slice(0, 10)) return 'La fecha del movimiento no puede ser futura.'
  if (previousDate && payload.date <= previousDate) return 'La fecha debe ser estrictamente posterior al movimiento activo anterior.'
  const type = types.find(t => t.id === payload.movement_type_id)
  if (!type) return 'Selecciona un tipo de movimiento activo.'
  const code = type.code
  const origin = payload.origin_farm_id && payload.origin_lot_id
  if (['TRANSFER', 'EXIT', 'SALE'].includes(code) && !origin) return 'Este tipo requiere finca y lote de origen histórico; el origen no puede añadirse ni cambiarse.'
  if (['EXIT', 'SALE'].includes(code) && (payload.destination_farm_id || payload.destination_lot_id)) return 'Una salida o venta no debe tener destino.'
  if (['TRANSFER', 'ENTRY', 'PURCHASE'].includes(code) && (!payload.destination_farm_id || !payload.destination_lot_id)) return 'Selecciona finca y lote de destino.'
  if (payload.destination_lot_id && !payload.destination_farm_id) return 'El lote destino requiere finca destino.'
  if (payload.destination_farm_id && (!farms.some(f => f.id === payload.destination_farm_id) || !lots.some(l => l.id === payload.destination_lot_id && l.farm_id === payload.destination_farm_id))) return 'Selecciona una finca y un lote de destino activos y compatibles.'
  if (code === 'TRANSFER' && payload.destination_farm_id === payload.origin_farm_id && payload.destination_lot_id === payload.origin_lot_id) return 'El origen y el destino de un traslado no pueden ser iguales.'
  if ((payload.reason?.length ?? 0) > 255) return 'El motivo admite hasta 255 caracteres.'
  return null
}
export function updatePayload(record: AnimalMovement): AnimalMovementUpdatePayload {
  return { animal_id: record.animal_id, movement_type_id: record.movement_type_id, date: record.date,
    origin_farm_id: record.origin_farm_id, origin_lot_id: record.origin_lot_id,
    destination_farm_id: record.destination_farm_id, destination_lot_id: record.destination_lot_id,
    reason: record.reason, notes: record.notes }
}
