import type { Animal } from './types'

export const pageSize = 24
export const filterKeys = ['status_id', 'gender_id', 'species_id', 'farm_id', 'lot_id'] as const
export type FilterKey = typeof filterKeys[number]
export type InventoryFilters = Record<FilterKey, string>
export const emptyFilters: InventoryFilters = { status_id: '', gender_id: '', species_id: '', farm_id: '', lot_id: '' }
export const displayValue = (value?: string | null) => value?.trim() || 'Sin datos'
export const identification = (animal: Animal) => animal.name?.trim() || animal.internal_id?.trim()
  || animal.official_tag?.trim() || animal.electronic_tag?.trim() || 'Sin identificación'
const normalize = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es').trim()

export function filterAnimals(animals: Animal[], query: string, filters: InventoryFilters) {
  const search = normalize(query)
  return animals.filter(animal => (!search || [animal.name, animal.internal_id, animal.official_tag, animal.electronic_tag]
    .some(value => value && normalize(value).includes(search)))
    && filterKeys.every(key => !filters[key] || (filters[key] === '__missing' ? !animal[key] : animal[key] === filters[key])))
}
const labels = { status_id: 'status', gender_id: 'gender', species_id: 'species', farm_id: 'farm', lot_id: 'lot' } as const
export function filterOptions(animals: Animal[], key: FilterKey) {
  const options = new Map<string, string>()
  for (const animal of animals) options.set(animal[key] || '__missing', displayValue(animal[labels[key]]))
  return [...options].sort((a, b) => a[1].localeCompare(b[1], 'es'))
}
export function isInventory(value: unknown): value is Animal[] {
  return Array.isArray(value) && value.every(row => row && typeof row === 'object'
    && typeof row.id === 'string' && /^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i.test(row.id)
    && typeof row.is_active === 'boolean'
    && filterKeys.every(key => row[key] === null || typeof row[key] === 'string')
    && ['name', 'internal_id', 'official_tag', 'electronic_tag', 'species', 'breed', 'gender', 'status', 'farm', 'lot']
      .every(key => row[key] === null || typeof row[key] === 'string'))
    && new Set(value.map(row => row.id)).size === value.length
}
