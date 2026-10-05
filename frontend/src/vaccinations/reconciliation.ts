import type { Vaccination, VaccinationUpdatePayload } from './types'
import { isVaccination, validDose } from './validation'

function decimal(value: string): string | null {
  if (!validDose(value)) return null
  const [whole, fraction = ''] = value.split('.')
  const integer = whole.replace(/^0+/, '') || '0'
  const digits = fraction.replace(/0+$/, '')
  return digits ? `${integer}.${digits}` : integer
}

// Match the existing contract: only null optional text becomes empty text.
// Do not trim historical values or use floating point decimal conversions.
export function vaccinationSnapshot(payload: VaccinationUpdatePayload): Readonly<VaccinationUpdatePayload> {
  const dose = decimal(payload.dose)
  if (dose === null) throw new Error('Dosis inválida para reconciliación.')
  return Object.freeze({
    animal_id: payload.animal_id,
    vaccine_name: payload.vaccine_name,
    application_date: payload.application_date,
    next_application_date: payload.next_application_date,
    dose,
    batch: payload.batch ?? '',
    veterinarian: payload.veterinarian ?? '',
    notes: payload.notes ?? '',
  })
}

export function matchesVaccinationSnapshot(record: Vaccination, vaccinationId: string, snapshot: Readonly<VaccinationUpdatePayload>): boolean {
  if (!isVaccination(record, snapshot.animal_id) || record.id !== vaccinationId) return false
  const persisted = vaccinationSnapshot(record)
  return (Object.keys(snapshot) as Array<keyof VaccinationUpdatePayload>).every((field) => persisted[field] === snapshot[field])
}
