// Gregorian civil-day arithmetic: no browser timezone, timestamps or clock.
function civilDay(iso: string | null): number | null {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null
  const [year, month, day] = iso.split('-').map(Number)
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const lengths = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > lengths[month - 1]) return null
  const previousYear = year - 1
  return previousYear * 365 + Math.floor(previousYear / 4) - Math.floor(previousYear / 100)
    + Math.floor(previousYear / 400) + lengths.slice(0, month - 1).reduce((sum, length) => sum + length, 0) + day
}

export function daysRemaining(expectedBirth: string, businessToday: string | null): number | null {
  const expected = civilDay(expectedBirth), today = civilDay(businessToday)
  return expected === null || today === null ? null : expected - today
}

export function remainingLabel(days: number | null): string {
  if (days === null) return 'Fecha operativa no disponible'
  if (days === 0) return 'Hoy · 0 días'
  if (days === 1) return 'En 1 día'
  if (days < 0) return `Hace ${Math.abs(days)} ${days === -1 ? 'día' : 'días'}`
  return `En ${days} días`
}

export function animalDistribution(total: number, active: number) {
  if (!Number.isSafeInteger(total) || !Number.isSafeInteger(active) || total < 0 || active < 0 || active > total) return null
  const activePercent = total === 0 ? 0 : Math.round(active / total * 1000) / 10
  return { active, other: total - active, activePercent, otherPercent: total === 0 ? 0 : Math.round((100 - activePercent) * 10) / 10 }
}

export const percentLabel = (value: number) => `${String(value).replace('.', ',')} %`
