import { isUUID, validDate } from '../breeding/validation'
import type { DashboardSummary, UpcomingBirth } from './types'

const object = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value)
const counts = ['total_animals', 'active_animals', 'pregnancies', 'births_this_month',
  'upcoming_births', 'vaccinations_due'] as const

export function isDashboardSummary(value: unknown): value is DashboardSummary {
  return object(value) && counts.every(key => Number.isSafeInteger(value[key]) && (value[key] as number) >= 0)
    && (value.average_weight === null || (typeof value.average_weight === 'string'
      && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value.average_weight)))
}

export function isUpcomingBirths(value: unknown): value is UpcomingBirth[] {
  return Array.isArray(value) && value.every(row => object(row) && isUUID(row.animal_id)
    && typeof row.animal === 'string' && !!row.animal.trim() && validDate(row.expected_birth))
}
