export interface VaccinationCreatePayload {
  animal_id: string
  vaccine_name: string
  application_date: string
  next_application_date?: string | null
  dose: string
  batch?: string | null
  veterinarian?: string | null
  notes?: string | null
}

export interface Vaccination {
  id: string
  animal_id: string
  vaccine_name: string
  application_date: string
  next_application_date: string | null
  dose: string
  batch: string | null
  veterinarian: string | null
  notes: string | null
  is_active: boolean
}
