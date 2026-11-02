import { isUUID, validDate } from '../breeding/validation'
import type { BirthCreatePayload, BirthRecord } from './types'

// Compare Decimal strings without floating point rounding.
export function decimal(value: unknown): string | null {
  if (typeof value !== 'string' || !/^-?\d+(?:\.\d+)?$/.test(value)) return null
  const negative = value.startsWith('-'), [whole, fraction = ''] = value.replace(/^-/, '').split('.')
  const digits = fraction.replace(/0+$/, '')
  const normalized = `${whole.replace(/^0+(?=\d)/, '')}${digits ? '.' + digits : ''}`
  return negative && normalized !== '0' ? `-${normalized}` : normalized
}
export function isBirth(value: unknown, motherId: string): value is BirthRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const b = value as Record<string, unknown>
  return isUUID(motherId) && isUUID(b.id) && isUUID(b.pregnancy_id) && b.mother_id === motherId
    && (b.calf_id === null || isUUID(b.calf_id)) && (b.calf_gender_id === null || isUUID(b.calf_gender_id))
    && validDate(b.birth_date) && decimal(b.birth_weight) !== null
    && typeof b.alive === 'boolean' && typeof b.dystocia === 'boolean' && (b.notes === null || typeof b.notes === 'string')
}
export function isHistory(value: unknown, motherId: string): value is BirthRecord[] {
  return Array.isArray(value) && value.every(b => isBirth(b, motherId)) && new Set(value.map(b => b.id)).size === value.length
}
export function normalizedPayload(p: BirthCreatePayload) {
  return { pregnancy_id: p.pregnancy_id, mother_id: p.mother_id, calf_id: p.calf_id ?? null,
    calf_gender_id: p.calf_gender_id ?? null, birth_date: p.birth_date, birth_weight: p.birth_weight,
    alive: p.alive, dystocia: p.dystocia, notes: p.notes === undefined ? null : p.notes }
}
export type PreparedPayload = ReturnType<typeof normalizedPayload>
export function matchesPayload(b: BirthRecord, p: PreparedPayload): boolean {
  return b.pregnancy_id === p.pregnancy_id && b.mother_id === p.mother_id
    && (p.calf_id !== null ? b.calf_id === p.calf_id : p.alive ? isUUID(b.calf_id) : b.calf_id === null)
    && b.calf_gender_id === p.calf_gender_id && b.birth_date === p.birth_date
    && decimal(b.birth_weight) === decimal(p.birth_weight) && b.alive === p.alive && b.dystocia === p.dystocia && b.notes === p.notes
}
export function payloadError(p: PreparedPayload, motherId: string, today: string | null, diagnosis?: string, breeding?: string): string | null {
  if (!validDate(today)) return 'La fecha operativa no está disponible.'
  if (!isUUID(p.pregnancy_id) || !isUUID(p.mother_id) || p.mother_id !== motherId
    || (p.calf_id !== null && !isUUID(p.calf_id)) || (p.calf_gender_id !== null && !isUUID(p.calf_gender_id))) return 'Selecciona relaciones válidas para esta madre.'
  if (!validDate(p.birth_date) || p.birth_date > today) return 'La fecha del parto debe ser válida y no futura.'
  if ((diagnosis && p.birth_date < diagnosis) || (breeding && p.birth_date < breeding)) return 'El parto no puede ser anterior al diagnóstico o reproducción.'
  if (decimal(p.birth_weight) === null || !/^\d{1,4}(?:\.\d{1,2})?$/.test(p.birth_weight) || Number(p.birth_weight) <= 0) return 'Indica un peso positivo de hasta 9999.99 kg y dos decimales.'
  if (typeof p.alive !== 'boolean' || typeof p.dystocia !== 'boolean' || (p.notes !== null && typeof p.notes !== 'string')) return 'Datos del parto inválidos.'
  if (!p.alive && p.calf_id !== null) return 'Un parto no vivo no puede asociar una cría existente.'
  if (p.calf_id === null && p.calf_gender_id === null) return 'Indica el sexo de la cría.'
  return null
}
