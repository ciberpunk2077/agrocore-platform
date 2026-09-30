import { apiRequest } from '../lib/api'
import type { AnimalMovement, AnimalMovementCreatePayload, MovementType } from './types'

export function getMovementTypes(accessToken: string): Promise<MovementType[]> {
  return apiRequest<MovementType[]>('/catalogs/movement-types', {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
}

export function getAnimalMovementHistory(
  animalId: string,
  accessToken: string,
): Promise<AnimalMovement[]> {
  return apiRequest<AnimalMovement[]>(`/animal-movements/animal/${animalId}/history`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
}

export function createAnimalMovement(
  data: AnimalMovementCreatePayload,
  accessToken: string,
): Promise<AnimalMovement> {
  return apiRequest<AnimalMovement>('/animal-movements/', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify(data),
  })
}
