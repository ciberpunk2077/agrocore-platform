import { apiRequest } from '../lib/api'
import { normalizeApiError } from '../lib/api-errors'
import type { BirthCreatePayload, BirthRecord } from './types'

export function createBirth(
  data: BirthCreatePayload,
  accessToken: string,
): Promise<BirthRecord> {
  return apiRequest<BirthRecord>('/births/', {
    method: 'POST',
    accessToken,
    body: JSON.stringify(data),
  })
}

export function getAnimalBirthHistory(
  animalId: string,
  accessToken: string,
  signal?: AbortSignal,
): Promise<BirthRecord[]> {
  return apiRequest<BirthRecord[]>(
    `/births/animal/${animalId}/history`,
    {
      accessToken,
      signal,
    },
  )
}

export function birthErrorMessage(cause: unknown, fallback: string): string {
  return normalizeApiError(cause, fallback).message
}
