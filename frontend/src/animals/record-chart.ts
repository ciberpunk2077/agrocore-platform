import { validDate } from '../breeding/validation'

export interface ChartPoint { date: string; value: string }

export function chartPoints(points: ChartPoint[]) {
  if (points.some(p => !p || typeof p.date !== 'string' || typeof p.value !== 'string'
    || !/^\d+(?:\.\d+)?$/.test(p.value) || !Number.isFinite(Number(p.value))
    || !validDate(p.date.slice(0, 10)) || !Number.isFinite(Date.parse(p.date))
    || (p.date.length !== 10 && !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(p.date)))) return null
  const ordered = [...points].sort((a, b) => Date.parse(a.date) - Date.parse(b.date))
  if (ordered.length < 2 || new Set(ordered.map(p => Date.parse(p.date))).size !== ordered.length) return null
  return ordered
}
