import type { Farm } from './types'
import { isUUID } from '../animal-movements/validation'

export const farmText = (value?: string | null) => value?.trim() || 'Sin datos'
export function isFarmInventory(value: unknown): value is Farm[] {
  return Array.isArray(value) && value.every(row => row && typeof row === 'object' && isUUID(row.id)
    && ['code', 'name', 'farm_type', 'city', 'state'].every(key => row[key] === null || typeof row[key] === 'string'))
    && new Set(value.map(row => row.id)).size === value.length
}
