import { apiRequest } from '../lib/api'
import { normalizeApiError } from '../lib/api-errors'
import type { PregnancyCreatePayload, PregnancyRecord } from './types'

export function createPregnancy(data: PregnancyCreatePayload, accessToken: string): Promise<PregnancyRecord> {
  return apiRequest<PregnancyRecord>('/pregnancies/', {
    method: 'POST',
    accessToken,
    body: JSON.stringify(data),
  })
}

export function abortPregnancy(pregnancyId: string, accessToken: string): Promise<PregnancyRecord> {
  return apiRequest<PregnancyRecord>(`/pregnancies/${pregnancyId}/abort`, {
    method: 'POST',
    accessToken,
  })
}

export function getAnimalPregnancyHistory(animalId: string, accessToken: string, signal?: AbortSignal): Promise<PregnancyRecord[]> {
  return apiRequest<PregnancyRecord[]>(`/pregnancies/animal/${animalId}/history`, {
    accessToken,
    signal,
  })
}

export function pregnancyErrorMessage(cause: unknown, fallback: string): string {
  return normalizeApiError(cause, fallback).message
}
