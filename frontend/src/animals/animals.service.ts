import { apiRequest } from '../lib/api'
import type { Animal, AnimalWritePayload } from './types'

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


export function createAnimal(
  data: AnimalWritePayload,
  accessToken: string,
): Promise<Animal> {
  return apiRequest<Animal>('/animals/', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(data),
  })
}

export function updateAnimal(
  animalId: string,
  data: AnimalWritePayload,
  accessToken: string,
): Promise<Animal> {
  return apiRequest<Animal>(`/animals/${animalId}`, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(data),
  })
}