import type { Vaccination, VaccinationUpdatePayload } from './types'
import { vaccinationToday } from './civil-date'

export function vaccinationFieldErrors(data: VaccinationUpdatePayload, birthDate: string | null): Record<string, string[]> {
  const errors: Record<string, string[]> = {}
  if (!data.vaccine_name.trim() || data.vaccine_name.length > 150) errors.vaccine_name = ['Introduce un nombre de vacuna de hasta 150 caracteres.']
  if (!validDose(data.dose)) errors.dose = ['Introduce una dosis positiva con hasta 6 enteros y 2 decimales (máximo 999999.99).']
  if (!validDate(data.application_date)) errors.application_date = ['Introduce una fecha válida.']
  else if (data.application_date > vaccinationToday()) errors.application_date = ['La fecha de aplicación no puede ser futura.']
  else if (birthDate && data.application_date < birthDate) errors.application_date = ['La fecha de aplicación no puede ser anterior al nacimiento del animal.']
  if (data.next_application_date !== null && (!validDate(data.next_application_date) || data.next_application_date <= data.application_date)) errors.next_application_date = ['La próxima fecha debe ser válida y posterior a la aplicación.']
  if ((data.batch?.length ?? 0) > 50) errors.batch = ['El lote admite hasta 50 caracteres.']
  if ((data.veterinarian?.length ?? 0) > 150) errors.veterinarian = ['El veterinario admite hasta 150 caracteres.']
  return errors
}

export function validDose(value: string): boolean {
  return /^\d+(?:\.\d{1,2})?$/.test(value)
    && value.split('.')[0].replace(/^0+/, '').length <= 6 && /[1-9]/.test(value)
}

export function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) return false
  const instant = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(instant.getTime()) && instant.toISOString().slice(0, 10) === value
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const optionalText = (value: unknown) => value === null || typeof value === 'string'

export function isVaccination(value: unknown, animalId: string): value is Vaccination {
  if (!value || typeof value !== 'object') return false
  const record = value as Record<string, unknown>
  return typeof record.id === 'string' && uuid.test(record.id)
    && record.animal_id === animalId && uuid.test(animalId)
    && typeof record.vaccine_name === 'string' && record.vaccine_name.length > 0 && record.vaccine_name.length <= 150
    && typeof record.application_date === 'string' && validDate(record.application_date)
    && (record.next_application_date === null || (typeof record.next_application_date === 'string' && validDate(record.next_application_date)))
    && typeof record.dose === 'string' && validDose(record.dose)
    && optionalText(record.batch) && optionalText(record.veterinarian) && optionalText(record.notes)
    && record.is_active === true
}
