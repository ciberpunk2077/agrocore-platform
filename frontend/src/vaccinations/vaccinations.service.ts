import { apiRequest } from '../lib/api'
import { normalizeApiError } from '../lib/api-errors'
import type { Vaccination, VaccinationCreatePayload, VaccinationUpdatePayload } from './types'
import { isVaccination } from './validation'

export async function deleteVaccination(vaccinationId: string, accessToken: string, signal?: AbortSignal): Promise<{ success: true }> {
  const result = await apiRequest<unknown>(`/vaccinations/${encodeURIComponent(vaccinationId)}`, {
    method: 'DELETE', accessToken, signal, expectedStatus: 200,
  })
  if (!result || typeof result !== 'object' || Array.isArray(result) || !('success' in result) || result.success !== true) {
    throw new Error('Eliminación no confirmada.')
  }
  return { success: true }
}

export async function getVaccination(vaccinationId: string, animalId: string, accessToken: string, signal?: AbortSignal): Promise<Vaccination> {
  const result = await apiRequest<unknown>(`/vaccinations/${encodeURIComponent(vaccinationId)}`, {
    accessToken, signal, expectedStatus: 200,
  })
  if (!isVaccination(result, animalId) || result.id !== vaccinationId) throw new Error('Respuesta de detalle inválida para esta vacunación o animal.')
  return result
}

export async function updateVaccination(vaccinationId: string, payload: VaccinationUpdatePayload, accessToken: string, signal?: AbortSignal): Promise<Vaccination> {
  const result = await apiRequest<unknown>(`/vaccinations/${encodeURIComponent(vaccinationId)}`, {
    method: 'PUT', accessToken, signal, expectedStatus: 200, body: JSON.stringify(payload),
  })
  if (!isVaccination(result, payload.animal_id) || result.id !== vaccinationId) throw new Error('Resultado de actualización no confirmado.')
  return result
}

export async function createVaccination(
  data: VaccinationCreatePayload,
  accessToken: string,
  signal?: AbortSignal,
): Promise<Vaccination> {
  const result = await apiRequest<unknown>('/vaccinations/', {
    method: 'POST',
    accessToken,
    signal,
    expectedStatus: 200,
    body: JSON.stringify(data),
  })
  if (!isVaccination(result, data.animal_id)) throw new Error('Respuesta de creación inesperada.')
  return result
}

export async function getAnimalVaccinationHistory(
  animalId: string,
  accessToken: string,
  signal?: AbortSignal,
): Promise<Vaccination[]> {
  const result = await apiRequest<unknown>(`/vaccinations/animal/${encodeURIComponent(animalId)}/history`, {
    accessToken,
    signal,
  })
  if (!Array.isArray(result) || !result.every((item) => isVaccination(item, animalId))) {
    throw new Error('Respuesta de historial inesperada o de otro animal.')
  }
  return result
}

export function vaccinationErrorMessage(cause: unknown, fallback: string): string {
  return normalizeApiError(cause, fallback).message
}
