import { ApiError, apiRequest } from '../lib/api'
import type { BirthCreatePayload, BirthRecord } from './types'

export function createBirth(
  data: BirthCreatePayload,
  accessToken: string,
): Promise<BirthRecord> {
  return apiRequest<BirthRecord>('/births/', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
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
      headers: { Authorization: `Bearer ${accessToken}` },
      signal,
    },
  )
}

export function birthErrorMessage(
  cause: unknown,
  fallback: string,
): string {
  if (
    cause instanceof ApiError &&
    cause.data &&
    typeof cause.data === 'object' &&
    'detail' in cause.data
  ) {
    const detail = cause.data.detail

    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
  }

  return fallback
}