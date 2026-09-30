import { ApiError, apiRequest } from '../lib/api'
import type { Vaccination, VaccinationCreatePayload } from './types'

export function createVaccination(
  data: VaccinationCreatePayload,
  accessToken: string,
): Promise<Vaccination> {
  return apiRequest<Vaccination>('/vaccinations/', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify(data),
  })
}

export function getAnimalVaccinationHistory(
  animalId: string,
  accessToken: string,
  signal?: AbortSignal,
): Promise<Vaccination[]> {
  return apiRequest<Vaccination[]>(`/vaccinations/animal/${animalId}/history`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    signal,
  })
}

export function vaccinationErrorMessage(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError && cause.data && typeof cause.data === 'object' && 'detail' in cause.data) {
    const detail = cause.data.detail
    if (typeof detail === 'string' && detail.trim()) return detail
  }
  return fallback
}
