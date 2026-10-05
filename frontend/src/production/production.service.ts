import { apiRequest } from '../lib/api'
import type { ProductionCreatePayload, ProductionRecord, ProductionType, ProductionUpdatePayload } from './types'

export function deleteProduction(recordId: string, accessToken: string, signal?: AbortSignal): Promise<{ success: boolean }> {
  return apiRequest(`/production/${encodeURIComponent(recordId)}`, { method: 'DELETE', accessToken, signal })
}

export function updateProduction(recordId: string, payload: ProductionUpdatePayload, accessToken: string, signal?: AbortSignal): Promise<ProductionRecord> {
  return apiRequest(`/production/${encodeURIComponent(recordId)}`, { method: 'PUT', accessToken, signal, body: JSON.stringify(payload) })
}

export function createProduction(payload: ProductionCreatePayload, accessToken: string, signal?: AbortSignal): Promise<ProductionRecord> {
  return apiRequest('/production/', { method: 'POST', accessToken, signal, body: JSON.stringify(payload) })
}

export function getAnimalProductionHistory(animalId: string, accessToken: string, signal?: AbortSignal): Promise<ProductionRecord[]> {
  return apiRequest(`/production/history/${encodeURIComponent(animalId)}`, { accessToken, signal })
}

export function getProductionTypes(accessToken: string, signal?: AbortSignal): Promise<ProductionType[]> {
  return apiRequest('/catalogs/production-types', { accessToken, signal })
}
