import { apiRequest } from '../lib/api'
import type {
  Weight,
  WeightCreatePayload,
  WeightUpdatePayload,
  WeightHistory,
  WeighingMethod,
} from './types'

export async function deleteWeight(weightId: string, accessToken: string, signal?: AbortSignal): Promise<{ success: true }> {
  const result = await apiRequest<unknown>(`/weights/${encodeURIComponent(weightId)}`, {
    method: 'DELETE', accessToken, signal, expectedStatus: 200,
  })
  if (!result || typeof result !== 'object' || !('success' in result) || result.success !== true) {
    throw new Error('Eliminación no confirmada.')
  }
  return { success: true }
}

export function updateWeight(weightId: string, payload: WeightUpdatePayload, accessToken: string, signal?: AbortSignal): Promise<Weight> {
  return apiRequest<Weight>(`/weights/${encodeURIComponent(weightId)}`, {
    method: 'PUT', accessToken, signal, body: JSON.stringify(payload),
  })
}

export function getWeight(
  weightId: string,
  accessToken: string,
  signal?: AbortSignal,
): Promise<Weight> {
  return apiRequest<Weight>(`/weights/${encodeURIComponent(weightId)}`, {
    accessToken,
    signal,
  })
}

export function getAnimalWeightHistory(
  animalId: string,
  accessToken: string,
  signal?: AbortSignal,
): Promise<WeightHistory[]> {
  return apiRequest<WeightHistory[]>(
    `/weights/animal/${animalId}/history`,
    {
      accessToken,
      signal,
    },
  )
}

export function getWeighingMethods(
  accessToken: string,
  signal?: AbortSignal,
): Promise<WeighingMethod[]> {
  return apiRequest<WeighingMethod[]>('/catalogs/weighing-methods', {
    accessToken,
    signal,
  })
}

export function createWeight(
  data: WeightCreatePayload,
  accessToken: string,
): Promise<Weight> {
  return apiRequest<Weight>('/weights/', {
    method: 'POST',
    accessToken,
    body: JSON.stringify(data),
  })
}
