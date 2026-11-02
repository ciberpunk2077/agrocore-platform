import { apiRequest } from '../lib/api'
import type { DashboardSummary, UpcomingBirth } from './types'
import { isDashboardSummary, isUpcomingBirths } from './validation'

export async function getDashboardSummary(
  accessToken: string,
  signal?: AbortSignal,
): Promise<DashboardSummary> {
  const data = await apiRequest<unknown>('/dashboard/summary', {
    method: 'GET', accessToken, signal, cache: 'no-store', expectedStatus: 200,
  })
  if (!isDashboardSummary(data)) throw new Error('Respuesta inválida del resumen del Dashboard.')
  return data
}

export async function getUpcomingBirths(
  accessToken: string,
  signal?: AbortSignal,
): Promise<UpcomingBirth[]> {
  const data = await apiRequest<unknown>('/dashboard/upcoming-births', {
    method: 'GET', accessToken, signal, cache: 'no-store', expectedStatus: 200,
  })
  if (!isUpcomingBirths(data)) throw new Error('Respuesta inválida de próximos partos.')
  return data
}
