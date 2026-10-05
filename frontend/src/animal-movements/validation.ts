import type { Animal, Farm, Lot } from '../animals/types'
import type { AnimalMovement, AnimalMovementCreatePayload, MovementType } from './types'

export const isUUID = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v)
const nullableUUID = (v: unknown) => v === null || isUUID(v)
const text = (v: unknown) => v === null || typeof v === 'string'
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const parentReference = (v: unknown) => v === undefined || v === null || (object(v) && isUUID(v.id)
  && text(v.internal_id) && text(v.name) && typeof v.is_active === 'boolean' && typeof v.is_deleted === 'boolean')
export function validDate(v: unknown): v is string {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v) || v.startsWith('0000')) return false
  const d = new Date(`${v}T00:00:00Z`)
  return Number.isFinite(d.getTime()) && d.toISOString().slice(0, 10) === v
}
export function isMovement(v: unknown, animalId: string): v is AnimalMovement {
  return object(v) && isUUID(v.id) && isUUID(animalId) && v.animal_id === animalId
    && isUUID(v.movement_type_id) && nullableUUID(v.origin_status_id)
    && ['origin_farm_id', 'origin_lot_id', 'destination_farm_id', 'destination_lot_id'].every(k => nullableUUID(v[k]))
    && validDate(v.date) && text(v.reason) && text(v.notes)
}
export function isHistory(v: unknown, animalId: string): v is AnimalMovement[] {
  return Array.isArray(v) && v.every(item => isMovement(item, animalId)) && new Set(v.map(item => item.id)).size === v.length
}
export function isMovementTypes(v: unknown): v is MovementType[] {
  return Array.isArray(v) && v.every(item => object(item) && isUUID(item.id) && typeof item.code === 'string' && typeof item.name === 'string')
    && new Set(v.map(item => item.id)).size === v.length
}
export function isFarms(v: unknown): v is Farm[] {
  return Array.isArray(v) && v.every(item => object(item) && isUUID(item.id) && isUUID(item.farm_type_id)
    && ['name', 'code', 'farm_type', 'description', 'address', 'city', 'state', 'country'].every(k => typeof item[k] === 'string'))
    && new Set(v.map(item => item.id)).size === v.length
}
export function isLots(v: unknown, organizationId: string): v is Lot[] {
  return Array.isArray(v) && v.every(item => object(item) && isUUID(item.id) && isUUID(item.farm_id)
    && isUUID(item.organization_id) && item.organization_id === organizationId
    && ['code', 'name', 'description'].every(k => typeof item[k] === 'string') && Number.isInteger(item.capacity))
    && new Set(v.map(item => item.id)).size === v.length
}
export function isAnimal(v: unknown, animalId: string): v is Animal {
  if (!object(v) || !isUUID(v.id) || v.id !== animalId || typeof v.is_active !== 'boolean') return false
  return ['species_id', 'breed_id', 'gender_id', 'status_id'].every(k => isUUID(v[k]))
    && ['farm_id', 'lot_id', 'mother_id', 'father_id'].every(k => nullableUUID(v[k]))
    && ['species', 'breed', 'gender', 'status'].every(k => typeof v[k] === 'string')
    && ['internal_id', 'official_tag', 'electronic_tag', 'name', 'farm', 'lot', 'notes'].every(k => text(v[k]))
    && (v.birth_date === null || validDate(v.birth_date))
    && (v.birth_weight === null || (typeof v.birth_weight === 'string' && /^\d+(?:\.\d+)?$/.test(v.birth_weight)))
    && parentReference(v.mother_reference) && parentReference(v.father_reference)
}
export function matchesAttempt(m: AnimalMovement, p: AnimalMovementCreatePayload, statusId: string | null): boolean {
  return m.animal_id === p.animal_id && m.origin_status_id === statusId && m.movement_type_id === p.movement_type_id
    && m.date === p.date && ['origin_farm_id', 'origin_lot_id', 'destination_farm_id', 'destination_lot_id', 'reason', 'notes'].every(k => {
      const key = k as keyof AnimalMovementCreatePayload
      const expected = p[key] ?? (k === 'reason' || k === 'notes' ? '' : null)
      return m[k as keyof AnimalMovement] === expected
    })
}
