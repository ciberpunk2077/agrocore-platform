import { apiRequest } from '../lib/api'
import type { Animal } from './types'

export function getAnimals(accessToken: string): Promise<Animal[]> {
  return apiRequest<Animal[]>('/animals/', {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}

export function getAnimal(
  animalId: string,
  accessToken: string,
): Promise<Animal> {
  return apiRequest<Animal>(`/animals/${animalId}`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}