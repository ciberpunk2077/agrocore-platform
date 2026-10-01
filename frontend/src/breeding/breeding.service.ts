import { ApiError, apiRequest } from '../lib/api'
import type { Animal } from '../animals/types'
import type { BreedingCreatePayload, BreedingEvent, BreedingType } from './types'

export function animalLabel(animal: Animal): string {
  return [animal.name?.trim(), animal.internal_id?.trim()].filter(Boolean).join(' · ') || animal.id
}

export function createBreeding(data: BreedingCreatePayload, accessToken: string): Promise<BreedingEvent> {
  return apiRequest<BreedingEvent>('/breeding/', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify(data),
  })
}

export function getBreedingTypes(accessToken: string): Promise<BreedingType[]> {
  return apiRequest<BreedingType[]>('/catalogs/breeding-types', {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
}

export function getAnimalBreedingHistory(animalId: string, accessToken: string, signal?: AbortSignal): Promise<BreedingEvent[]> {
  return apiRequest<BreedingEvent[]>(`/breeding/animal/${animalId}/history`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    signal,
  })
}

export function breedingErrorMessage(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError && cause.data && typeof cause.data === 'object' && 'detail' in cause.data) {
    const detail = cause.data.detail
    if (typeof detail === 'string' && detail.trim()) return detail
  }
  return fallback
}
