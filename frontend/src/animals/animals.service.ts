import { apiRequest } from '../lib/api'
import type { Animal, AnimalParentCandidate, AnimalUpdatePayload, AnimalWritePayload } from './types'

export function getAnimals(accessToken: string, signal?: AbortSignal): Promise<Animal[]> {
  return apiRequest<Animal[]>('/animals/', {
    accessToken,
    signal,
  })
}

export function getAnimal(
  animalId: string,
  accessToken: string,
): Promise<Animal> {
  return apiRequest<Animal>(`/animals/${animalId}`, {
    accessToken,
  })
}


export function createAnimal(
  data: AnimalWritePayload,
  accessToken: string,
): Promise<Animal> {
  return apiRequest<Animal>('/animals/', {
    method: 'POST',
    accessToken,
    body: JSON.stringify(data),
  })
}

export function updateAnimal(
  animalId: string,
  data: AnimalUpdatePayload,
  accessToken: string,
): Promise<Animal> {
  return apiRequest<Animal>(`/animals/${animalId}`, {
    method: 'PUT',
    accessToken,
    body: JSON.stringify(data),
  })
}
export function getParentCandidates(accessToken: string): Promise<AnimalParentCandidate[]> {
  return apiRequest<AnimalParentCandidate[]>('/animals/parents/candidates', { accessToken })
}
