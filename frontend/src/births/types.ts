export interface BirthCreatePayload {
  pregnancy_id: string
  mother_id: string
  calf_id?: string | null
  calf_gender_id?: string | null
  birth_date: string
  birth_weight: string
  alive: boolean
  dystocia: boolean
  notes?: string | null
}

export interface BirthRecord {
  id: string
  pregnancy_id: string
  mother_id: string
  calf_id: string | null
  calf_gender_id: string | null
  birth_date: string
  birth_weight: string
  alive: boolean
  dystocia: boolean
  notes: string | null
}