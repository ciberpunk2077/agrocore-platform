import { apiRequest, ApiError } from '../lib/api'
import { normalizeApiError } from '../lib/api-errors'
import type { PregnancyCreatePayload, PregnancyRecord } from './types'
import { isHistory, isPregnancy, matchesPayload, normalizedPayload } from './validation'
import { isUUID } from '../breeding/validation'

export class InvalidPregnancyResponse extends Error {
  constructor() { super('Respuesta inválida de Gestación.') }
}
export const uncertainCreate = (cause: unknown) => !(cause instanceof ApiError && [400, 401, 403, 404, 422].includes(cause.status))

export async function getPregnancyDetail(pregnancyId: string, animalId: string, breedingId: string, accessToken: string, signal?: AbortSignal): Promise<PregnancyRecord> {
  if (![pregnancyId, animalId, breedingId].every(isUUID)) throw new InvalidPregnancyResponse()
  const result = await apiRequest<unknown>(`/pregnancies/${encodeURIComponent(pregnancyId)}`, {
    accessToken, signal, cache: 'no-store', expectedStatus: 200,
  })
  if (!isPregnancy(result, animalId) || result.id !== pregnancyId || result.breeding_id !== breedingId) throw new InvalidPregnancyResponse()
  return result
}

export async function createPregnancy(data: PregnancyCreatePayload, accessToken: string, signal?: AbortSignal): Promise<PregnancyRecord> {
  const payload = normalizedPayload(data)
  const result = await apiRequest<unknown>('/pregnancies/', {
    method: 'POST',
    accessToken,
    signal, expectedStatus: 200, body: JSON.stringify(payload),
  })
  if (!isPregnancy(result, payload.animal_id) || result.status !== 'ACTIVE' || !matchesPayload(result, payload)) throw new InvalidPregnancyResponse()
  return result
}

export async function abortPregnancy(fresh: Readonly<PregnancyRecord>, accessToken: string, signal?: AbortSignal): Promise<PregnancyRecord> {
  if (!isPregnancy(fresh, fresh.animal_id) || fresh.status !== 'ACTIVE') throw new InvalidPregnancyResponse()
  const result = await apiRequest<unknown>(`/pregnancies/${encodeURIComponent(fresh.id)}/abort`, {
    method: 'POST',
    accessToken,
    signal, expectedStatus: 200,
  })
  if (!isPregnancy(result, fresh.animal_id) || result.id !== fresh.id || result.status !== 'ABORTED'
    || !matchesPayload(result, { ...normalizedPayload(fresh), notes: fresh.notes })) throw new InvalidPregnancyResponse()
  return result
}

export async function getAnimalPregnancyHistory(animalId: string, accessToken: string, signal?: AbortSignal): Promise<PregnancyRecord[]> {
  const result = await apiRequest<unknown>(`/pregnancies/animal/${encodeURIComponent(animalId)}/history`, {
    accessToken,
    signal,
    expectedStatus: 200,
  })
  if (!isHistory(result, animalId)) throw new InvalidPregnancyResponse()
  return result
}

export function pregnancyErrorMessage(cause: unknown, fallback: string): string {
  return normalizeApiError(cause, fallback).message
}
