import { apiRequest } from '../lib/api'
import type { Lot, LotCreatePayload, LotUpdatePayload } from './types'

export function deleteLot(lotId: string, accessToken: string): Promise<{ success: boolean }> {
  return apiRequest(`/lots/${encodeURIComponent(lotId)}`, { method: 'DELETE', accessToken })
}

export function getLots(accessToken: string): Promise<Lot[]> {
  return apiRequest<Lot[]>('/lots/', { accessToken })
}

export function getLot(lotId: string, accessToken: string): Promise<Lot> {
  return apiRequest<Lot>(`/lots/${encodeURIComponent(lotId)}`, { accessToken })
}

export function createLot(payload: LotCreatePayload, accessToken: string): Promise<Lot> {
  return apiRequest<Lot>('/lots/', { method: 'POST', body: JSON.stringify(payload), accessToken })
}

export function updateLot(lotId: string, payload: LotUpdatePayload, accessToken: string): Promise<Lot> {
  return apiRequest<Lot>(`/lots/${encodeURIComponent(lotId)}`, { method: 'PUT', body: JSON.stringify(payload), accessToken })
}
