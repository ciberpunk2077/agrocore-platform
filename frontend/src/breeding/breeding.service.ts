import { apiRequest } from '../lib/api'
import { normalizeApiError } from '../lib/api-errors'
import type { Animal } from '../animals/types'
import type { BreedingCreatePayload, BreedingEvent, BreedingType } from './types'

export function animalLabel(animal: Animal): string {
  return [animal.name?.trim(), animal.internal_id?.trim()].filter(Boolean).join(' · ') || animal.id
}

export function createBreeding(data: BreedingCreatePayload, accessToken: string): Promise<BreedingEvent> {
  return apiRequest<BreedingEvent>('/breeding/', {
    method: 'POST',
    accessToken,
    body: JSON.stringify(data),
  })
}

export function getBreedingTypes(accessToken: string): Promise<BreedingType[]> {
  return apiRequest<BreedingType[]>('/catalogs/breeding-types', {
    accessToken,
  })
}

export function getAnimalBreedingHistory(animalId: string, accessToken: string, signal?: AbortSignal): Promise<BreedingEvent[]> {
  return apiRequest<BreedingEvent[]>(`/breeding/animal/${animalId}/history`, {
    accessToken,
    signal,
  })
}

export function breedingErrorMessage(cause: unknown, fallback: string): string {
  return normalizeApiError(cause, fallback).message
}
