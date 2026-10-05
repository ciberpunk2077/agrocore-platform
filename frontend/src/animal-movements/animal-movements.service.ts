import { apiRequest, ApiError } from '../lib/api'
import { isAnimal, isFarms, isHistory, isLots, isMovement, isMovementTypes, matchesAttempt } from './validation'
import type { AnimalMovementCreatePayload, AnimalMovementUpdatePayload } from './types'

export class InvalidMovementResponse extends Error {
  constructor() { super('Respuesta inválida de Animal Movements.') }
}
export const uncertainCreate = (cause: unknown) => !(cause instanceof ApiError && [400, 401, 403, 404, 422].includes(cause.status))

export async function getMovementTypes(accessToken: string, signal?: AbortSignal) {
  const data = await apiRequest<unknown>('/catalogs/movement-types', { accessToken, signal, expectedStatus: 200 })
  if (!isMovementTypes(data)) throw new InvalidMovementResponse()
  return data
}
export async function getMovementFarms(accessToken: string, signal?: AbortSignal) {
  const data = await apiRequest<unknown>('/farms/', { accessToken, signal, expectedStatus: 200 })
  if (!isFarms(data)) throw new InvalidMovementResponse()
  return data
}
export async function getMovementLots(accessToken: string, organizationId: string, signal?: AbortSignal) {
  const data = await apiRequest<unknown>('/lots/', { accessToken, signal, expectedStatus: 200 })
  if (!isLots(data, organizationId)) throw new InvalidMovementResponse()
  return data
}
export async function getAnimalMovementHistory(animalId: string, accessToken: string, signal?: AbortSignal) {
  const data = await apiRequest<unknown>(`/animal-movements/animal/${encodeURIComponent(animalId)}/history`, { accessToken, signal, expectedStatus: 200 })
  if (!isHistory(data, animalId)) throw new InvalidMovementResponse()
  return data
}
export async function getMovementAnimal(animalId: string, accessToken: string, signal?: AbortSignal) {
  const data = await apiRequest<unknown>(`/animals/${encodeURIComponent(animalId)}`, { accessToken, signal, expectedStatus: 200 })
  if (!isAnimal(data, animalId)) throw new InvalidMovementResponse()
  return data
}
export async function createAnimalMovement(data: AnimalMovementCreatePayload, statusId: string, accessToken: string, signal?: AbortSignal) {
  const result = await apiRequest<unknown>('/animal-movements/', { method: 'POST', accessToken, signal, expectedStatus: 200, body: JSON.stringify(data) })
  if (!isMovement(result, data.animal_id) || !matchesAttempt(result, data, statusId)) throw new InvalidMovementResponse()
  return result
}

export async function getAnimalMovement(movementId: string, animalId: string, accessToken: string, signal?: AbortSignal) {
  const result = await apiRequest<unknown>(`/animal-movements/${encodeURIComponent(movementId)}`, { accessToken, signal, expectedStatus: 200 })
  if (!isMovement(result, animalId) || result.id !== movementId) throw new InvalidMovementResponse()
  return result
}

export async function updateAnimalMovement(movementId: string, data: AnimalMovementUpdatePayload, originStatusId: string | null, accessToken: string, signal?: AbortSignal) {
  const result = await apiRequest<unknown>(`/animal-movements/${encodeURIComponent(movementId)}`, {
    method: 'PUT', accessToken, signal, expectedStatus: 200, body: JSON.stringify(data),
  })
  if (!isMovement(result, data.animal_id) || result.id !== movementId || !matchesAttempt(result, data, originStatusId)) throw new InvalidMovementResponse()
  return result
}

export async function deleteAnimalMovement(movementId: string, accessToken: string, signal?: AbortSignal): Promise<void> {
  const result = await apiRequest<unknown>(`/animal-movements/${encodeURIComponent(movementId)}`, {
    method: 'DELETE', accessToken, signal, expectedStatus: 200,
  })
  if (!result || typeof result !== 'object' || Array.isArray(result) || Object.keys(result).length !== 1
    || !('success' in result) || result.success !== true) throw new InvalidMovementResponse()
}
