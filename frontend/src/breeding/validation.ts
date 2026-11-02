import type { Animal, Gender } from '../animals/types'
import type { BreedingCreatePayload, BreedingEvent, BreedingType } from './types'

const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
export const isUUID = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v)
const nullableUUID = (v: unknown) => v === null || isUUID(v)
const nullableText = (v: unknown) => v === null || typeof v === 'string'
export function validDate(v: unknown): v is string {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v) || v.startsWith('0000')) return false
  const date = new Date(`${v}T00:00:00Z`)
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === v
}
export function isBreeding(v: unknown, animalId: string): v is BreedingEvent {
  // READ validates the contract, not new business rules on historical records.
  return object(v) && isUUID(v.id) && isUUID(animalId) && v.animal_id === animalId
    && isUUID(v.breeding_type_id) && nullableUUID(v.male_id) && validDate(v.date)
    && (v.expected_birth === null || validDate(v.expected_birth)) && nullableText(v.technician) && nullableText(v.notes)
}
export function isHistory(v: unknown, animalId: string): v is BreedingEvent[] {
  return Array.isArray(v) && v.every(item => isBreeding(item, animalId)) && new Set(v.map(item => item.id)).size === v.length
}
export function isCatalog(v: unknown): v is BreedingType[] & Gender[] {
  return Array.isArray(v) && v.every(item => object(item) && isUUID(item.id)
    && typeof item.code === 'string' && typeof item.name === 'string') && new Set(v.map(item => item.id)).size === v.length
}
const parent = (v: unknown) => v === undefined || v === null || (object(v) && isUUID(v.id)
  && nullableText(v.internal_id) && nullableText(v.name) && typeof v.is_active === 'boolean' && typeof v.is_deleted === 'boolean')
export function isAnimal(v: unknown, expectedId?: string): v is Animal {
  return object(v) && isUUID(v.id) && (expectedId === undefined || v.id === expectedId) && typeof v.is_active === 'boolean'
    && ['species_id', 'breed_id', 'gender_id', 'status_id'].every(k => isUUID(v[k]))
    && ['species', 'breed', 'gender', 'status'].every(k => typeof v[k] === 'string')
    && ['farm_id', 'lot_id', 'mother_id', 'father_id'].every(k => nullableUUID(v[k]))
    && ['internal_id', 'official_tag', 'electronic_tag', 'name', 'farm', 'lot', 'notes'].every(k => nullableText(v[k]))
    && (v.birth_date === null || validDate(v.birth_date))
    && (v.birth_weight === null || (typeof v.birth_weight === 'string' && /^\d+(?:\.\d+)?$/.test(v.birth_weight)))
    && parent(v.mother_reference) && parent(v.father_reference)
}
export function isAnimals(v: unknown): v is Animal[] {
  return Array.isArray(v) && v.every(item => isAnimal(item)) && new Set(v.map(item => item.id)).size === v.length
}
export function normalizedPayload(p: BreedingCreatePayload) {
  return { animal_id: p.animal_id, breeding_type_id: p.breeding_type_id, date: p.date,
    male_id: p.male_id ?? null, expected_birth: p.expected_birth ?? null,
    technician: p.technician === undefined ? '' : p.technician, notes: p.notes === undefined ? '' : p.notes }
}
export type PreparedPayload = ReturnType<typeof normalizedPayload>
export function matchesPayload(record: BreedingEvent, payload: BreedingCreatePayload) {
  const normalized = normalizedPayload(payload)
  return (Object.keys(normalized) as (keyof PreparedPayload)[]).every(key => record[key] === normalized[key])
}
export function payloadError(p: PreparedPayload, animalId: string, businessToday: string | null): string | null {
  if (!validDate(businessToday)) return 'La fecha operativa de la organización no está disponible.'
  if (p.animal_id !== animalId || !isUUID(p.animal_id) || !isUUID(p.breeding_type_id)
    || !nullableUUID(p.male_id) || p.male_id === animalId) return 'Selecciona relaciones válidas para este animal.'
  if (!validDate(p.date) || p.date > businessToday) return 'La fecha del evento reproductivo no puede ser futura y debe ser válida.'
  if (p.expected_birth !== null && (!validDate(p.expected_birth) || p.expected_birth <= p.date)) return 'La fecha estimada de parto debe ser posterior a la fecha del evento reproductivo.'
  if (typeof p.technician !== 'string' || Array.from(p.technician).length > 150) return 'El técnico admite un máximo de 150 caracteres.'
  if (typeof p.notes !== 'string') return 'Las notas deben ser texto.'
  return null
}
