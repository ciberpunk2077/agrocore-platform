import type { Lot } from './types'

const normalize = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es').trim()
export function filterLots(lots: Lot[], query: string, farmId: string) {
  const search = normalize(query)
  return lots.filter(lot => (!farmId || lot.farm_id === farmId)
    && (!search || [lot.name, lot.code].some(value => normalize(value).includes(search))))
}
export function totalCapacity(lots: Lot[]) {
  if (!lots.every(lot => Number.isSafeInteger(lot.capacity) && lot.capacity >= 0)) return null
  const total = lots.reduce((sum, lot) => sum + lot.capacity, 0)
  return Number.isSafeInteger(total) ? total : null
}
