import { apiRequest } from '../lib/api'
import type { Farm, FarmCreatePayload, FarmUpdatePayload, FarmType } from './types'

export function deleteFarm(farmId: string, accessToken: string): Promise<{ success: boolean }> {
  return apiRequest(`/farms/${encodeURIComponent(farmId)}`, { method: 'DELETE', accessToken })
}

export function getFarms(accessToken: string): Promise<Farm[]> {
  return apiRequest<Farm[]>('/farms/', { accessToken })
}

export function getFarm(farmId: string, accessToken: string): Promise<Farm> {
  return apiRequest<Farm>(`/farms/${encodeURIComponent(farmId)}`, { accessToken })
}

export function getFarmTypes(accessToken: string): Promise<FarmType[]> {
  return apiRequest<FarmType[]>('/catalogs/farm-types', { accessToken })
}

export function createFarm(payload: FarmCreatePayload, accessToken: string): Promise<Farm> {
  return apiRequest<Farm>('/farms/', { method: 'POST', body: JSON.stringify(payload), accessToken })
}

export function updateFarm(farmId: string, payload: FarmUpdatePayload, accessToken: string): Promise<Farm> {
  return apiRequest<Farm>(`/farms/${encodeURIComponent(farmId)}`, { method: 'PUT', body: JSON.stringify(payload), accessToken })
}
