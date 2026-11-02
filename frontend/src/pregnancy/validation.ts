import { isUUID, validDate } from '../breeding/validation'
import type { PregnancyCreatePayload, PregnancyRecord } from './types'

export function isPregnancy(v: unknown, animalId: string): v is PregnancyRecord {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return false
  const p = v as Record<string, unknown>
  return isUUID(animalId) && isUUID(p.id) && isUUID(p.breeding_id) && p.animal_id === animalId
    && validDate(p.diagnosis_date) && validDate(p.expected_birth) && typeof p.confirmed === 'boolean'
    && (p.notes === null || typeof p.notes === 'string') && ['ACTIVE', 'FINISHED', 'ABORTED'].includes(p.status as string)
}
export function isHistory(v: unknown, animalId: string): v is PregnancyRecord[] {
  return Array.isArray(v) && v.every(p => isPregnancy(p, animalId)) && new Set(v.map(p => p.id)).size === v.length
}
export function normalizedPayload(p: PregnancyCreatePayload) {
  return { animal_id: p.animal_id, breeding_id: p.breeding_id, diagnosis_date: p.diagnosis_date,
    expected_birth: p.expected_birth, confirmed: p.confirmed,
    notes: typeof p.notes === 'string' ? p.notes.trim() || null : p.notes ?? null }
}
export type PreparedPayload = ReturnType<typeof normalizedPayload>
export function matchesPayload(record: PregnancyRecord, p: PreparedPayload) {
  return (Object.keys(p) as (keyof PreparedPayload)[]).every(k => record[k] === p[k])
}
export function payloadError(p: PreparedPayload, animalId: string, today: string | null, breedingDate?: string) {
  if (!validDate(today)) return 'La fecha operativa de la organización no está disponible.'
  if (!isUUID(p.animal_id) || p.animal_id !== animalId || !isUUID(p.breeding_id)) return 'Selecciona relaciones válidas para este animal.'
  if (!validDate(p.diagnosis_date) || p.diagnosis_date > today) return 'La fecha de diagnóstico no puede ser futura y debe ser válida.'
  if (breedingDate && p.diagnosis_date < breedingDate) return 'La fecha de diagnóstico no puede ser anterior al evento reproductivo.'
  if (!validDate(p.expected_birth) || p.expected_birth <= p.diagnosis_date) return 'La fecha estimada de parto debe ser posterior a la fecha de diagnóstico.'
  if (p.confirmed !== true) return 'Solo se puede registrar una gestación confirmada.'
  if (p.notes !== null && typeof p.notes !== 'string') return 'Las notas deben ser texto o null.'
  return null
}
