import type { Animal } from '../animals/types'

export function animalName(animal: Animal): string {
  return [animal.name?.trim(), animal.internal_id?.trim()].filter(Boolean).join(' · ')
    || animal.official_tag?.trim() || animal.electronic_tag?.trim() || 'Animal con referencia registrada'
}
