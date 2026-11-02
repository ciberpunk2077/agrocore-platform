import { apiRequest, ApiError } from '../lib/api'
import { normalizeApiError } from '../lib/api-errors'
import type { Animal } from '../animals/types'
import type { BreedingCreatePayload, BreedingEvent, BreedingType } from './types'
import { isAnimal, isAnimals, isBreeding, isCatalog, isHistory, isUUID, matchesPayload, normalizedPayload } from './validation'

export class InvalidBreedingResponse extends Error {
  constructor() { super('Respuesta inválida de Reproducción.') }
}
export const uncertainCreate = (cause: unknown) => !(cause instanceof ApiError && [400, 401, 403, 404, 422].includes(cause.status))

export function animalLabel(animal: Animal): string {
  return [animal.name?.trim(), animal.internal_id?.trim()].filter(Boolean).join(' · ') || animal.id
}

export async function createBreeding(data: BreedingCreatePayload, accessToken: string, signal?: AbortSignal): Promise<BreedingEvent> {
  const payload = normalizedPayload(data)
  const result = await apiRequest<unknown>('/breeding/', {
    method: 'POST',
    accessToken,
    signal, expectedStatus: 200, body: JSON.stringify(payload),
  })
  if (!isBreeding(result, payload.animal_id) || !matchesPayload(result, payload)) throw new InvalidBreedingResponse()
  return result
}

export async function getBreedingTypes(accessToken: string, signal?: AbortSignal): Promise<BreedingType[]> {
  const result = await apiRequest<unknown>('/catalogs/breeding-types', { accessToken, signal, expectedStatus: 200 })
  if (!isCatalog(result)) throw new InvalidBreedingResponse()
  return result
}

export async function getAnimalBreedingHistory(animalId: string, accessToken: string, signal?: AbortSignal): Promise<BreedingEvent[]> {
  const result = await apiRequest<unknown>(`/breeding/animal/${encodeURIComponent(animalId)}/history`, { accessToken, signal, expectedStatus: 200 })
  if (!isHistory(result, animalId)) throw new InvalidBreedingResponse()
  return result
}

export async function getBreedingEvent(eventId: string, animalId: string, accessToken: string, signal?: AbortSignal): Promise<BreedingEvent> {
  if (!isUUID(eventId) || !isUUID(animalId)) throw new InvalidBreedingResponse()
  const result = await apiRequest<unknown>(`/breeding/${encodeURIComponent(eventId)}`, {
    accessToken, signal, cache: 'no-store', expectedStatus: 200,
  })
  if (!isBreeding(result, animalId) || result.id !== eventId) throw new InvalidBreedingResponse()
  return result
}

export async function getBreedingAnimal(animalId: string, accessToken: string, signal?: AbortSignal): Promise<Animal> {
  // Animal responses omit organization_id; the authenticated tenant-scoped endpoint is authoritative.
  const result = await apiRequest<unknown>(`/animals/${encodeURIComponent(animalId)}`, { accessToken, signal, expectedStatus: 200 })
  if (!isAnimal(result, animalId)) throw new InvalidBreedingResponse()
  return result
}
export async function getBreedingAnimals(accessToken: string, signal?: AbortSignal) {
  const result = await apiRequest<unknown>('/animals/', { accessToken, signal, expectedStatus: 200 })
  if (!isAnimals(result)) throw new InvalidBreedingResponse()
  return result
}
export async function getBreedingGenders(accessToken: string, signal?: AbortSignal) {
  const result = await apiRequest<unknown>('/catalogs/genders', { accessToken, signal, expectedStatus: 200 })
  if (!isCatalog(result)) throw new InvalidBreedingResponse()
  return result
}

export function breedingErrorMessage(cause: unknown, fallback: string): string {
  return normalizeApiError(cause, fallback).message
}
