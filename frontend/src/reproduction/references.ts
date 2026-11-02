import { getBreedingAnimal, getBreedingEvent, getBreedingGenders, getBreedingTypes } from '../breeding/breeding.service'
import { animalName } from './reference-labels'

export type ReferenceKind = 'animal' | 'event' | 'gender' | 'type'

export async function resolveReference(kind: ReferenceKind, id: string, animalId: string | undefined, access: string, signal: AbortSignal) {
  if (kind === 'animal') return animalName(await getBreedingAnimal(id, access, signal))
  if (kind === 'event') {
    if (!animalId) return null
    const event = await getBreedingEvent(id, animalId, access, signal)
    const types = await getBreedingTypes(access, signal).catch(() => [])
    return ['Servicio del ' + event.date.split('-').reverse().join('/'), types.find(t => t.id === event.breeding_type_id)?.name].filter(Boolean).join(' · ')
  }
  const catalog = await (kind === 'gender' ? getBreedingGenders : getBreedingTypes)(access, signal)
  return catalog.find(item => item.id === id)?.name ?? null
}
