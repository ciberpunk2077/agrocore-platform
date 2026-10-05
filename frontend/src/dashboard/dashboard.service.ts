import { apiRequest } from '../lib/api'
import type { DashboardSummary, UpcomingBirth } from './types'

export function getDashboardSummary(
  accessToken: string,
): Promise<DashboardSummary> {
  return apiRequest<DashboardSummary>('/dashboard/summary', {
    accessToken,
  })
}

export function getUpcomingBirths(
  accessToken: string,
): Promise<UpcomingBirth[]> {
  return apiRequest<UpcomingBirth[]>('/dashboard/upcoming-births', {
    accessToken,
  })
}