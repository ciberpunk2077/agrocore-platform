import { apiRequest } from '../lib/api'
import type { WeightHistory, WeighingMethod } from './types'

export function getAnimalWeightHistory(
  animalId: string,
  accessToken: string,
): Promise<WeightHistory[]> {
  return apiRequest<WeightHistory[]>(
    `/weights/animal/${animalId}/history`,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    },
  )
}

export function getWeighingMethods(
  accessToken: string,
): Promise<WeighingMethod[]> {
  return apiRequest<WeighingMethod[]>('/catalogs/weighing-methods', {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}