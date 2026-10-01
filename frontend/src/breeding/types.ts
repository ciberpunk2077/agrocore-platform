export interface BreedingType {
  id: string
  code: string
  name: string
}

export interface BreedingCreatePayload {
  animal_id: string
  male_id?: string | null
  breeding_type_id: string
  date: string
  expected_birth?: string | null
  technician?: string
  notes?: string
}

export interface BreedingEvent {
  id: string
  animal_id: string
  male_id: string | null
  breeding_type_id: string
  date: string
  expected_birth: string | null
  technician: string | null
  notes: string | null
}
