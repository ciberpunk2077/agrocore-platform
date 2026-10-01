import { ApiError, apiRequest } from '../lib/api'
import type { PregnancyCreatePayload, PregnancyRecord } from './types'

export function createPregnancy(data: PregnancyCreatePayload, accessToken: string): Promise<PregnancyRecord> {
  return apiRequest<PregnancyRecord>('/pregnancies/', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify(data),
  })
}

export function abortPregnancy(pregnancyId: string, accessToken: string): Promise<PregnancyRecord> {
  return apiRequest<PregnancyRecord>(`/pregnancies/${pregnancyId}/abort`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
  })
}

export function getAnimalPregnancyHistory(animalId: string, accessToken: string, signal?: AbortSignal): Promise<PregnancyRecord[]> {
  return apiRequest<PregnancyRecord[]>(`/pregnancies/animal/${animalId}/history`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    signal,
  })
}

export function pregnancyErrorMessage(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError && cause.data && typeof cause.data === 'object' && 'detail' in cause.data) {
    const detail = cause.data.detail
    if (typeof detail === 'string' && detail.trim()) return detail
  }
  return fallback
}
