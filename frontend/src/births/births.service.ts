import { apiRequest, ApiError } from '../lib/api'
import { normalizeApiError } from '../lib/api-errors'
import { isUUID } from '../breeding/validation'
import { isBirth, isHistory, matchesPayload, normalizedPayload } from './validation'
import type { BirthCreatePayload, BirthRecord } from './types'

export class InvalidBirthResponse extends Error {
  constructor() { super('Respuesta inválida de Partos.') }
}
export const uncertainCreate = (cause: unknown) => !(cause instanceof ApiError && [400, 401, 403, 404, 422].includes(cause.status))
export async function getBirthDetail(birthId: string, motherId: string, accessToken: string, signal?: AbortSignal): Promise<BirthRecord> {
  if (!isUUID(birthId) || !isUUID(motherId)) throw new InvalidBirthResponse()
  const result = await apiRequest<unknown>(`/births/${encodeURIComponent(birthId)}`, { accessToken, signal, cache: 'no-store', expectedStatus: 200 })
  if (!isBirth(result, motherId) || result.id !== birthId) throw new InvalidBirthResponse()
  return result
}
export async function createBirth(data: BirthCreatePayload, accessToken: string, signal?: AbortSignal): Promise<BirthRecord> {
  const payload = normalizedPayload(data)
  const result = await apiRequest<unknown>('/births/', { method: 'POST', accessToken, signal, expectedStatus: 200, body: JSON.stringify(payload) })
  if (!isBirth(result, payload.mother_id) || !matchesPayload(result, payload)) throw new InvalidBirthResponse()
  return result
}
export async function getAnimalBirthHistory(animalId: string, accessToken: string, signal?: AbortSignal): Promise<BirthRecord[]> {
  if (!isUUID(animalId)) throw new InvalidBirthResponse()
  const result = await apiRequest<unknown>(`/births/animal/${encodeURIComponent(animalId)}/history`, { accessToken, signal, cache: 'no-store', expectedStatus: 200 })
  if (!isHistory(result, animalId)) throw new InvalidBirthResponse()
  return result
}
export function birthErrorMessage(cause: unknown, fallback: string): string {
  return normalizeApiError(cause, fallback).message
}
