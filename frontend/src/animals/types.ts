export interface AnimalParentReference {
  id: string
  internal_id: string | null
  name: string | null
  is_active: boolean
  is_deleted: boolean
}

export interface Animal {
  id: string
  internal_id: string | null
  official_tag: string | null
  electronic_tag: string | null
  name: string | null

  species_id: string
  species: string

  breed_id: string
  breed: string

  gender_id: string
  gender: string

  status_id: string
  status: string

  farm_id: string | null
  farm: string | null

  lot_id: string | null
  lot: string | null

  birth_date: string | null
  birth_weight: string | null

  mother_id: string | null
  father_id: string | null
  mother_reference?: AnimalParentReference | null
  father_reference?: AnimalParentReference | null

  notes: string | null
  is_active: boolean
}


export interface AnimalWritePayload {
  farm_id: string
  lot_id: string
  species_id: string
  breed_id: string
  gender_id: string
  status_id: string
  internal_id: string

  official_tag?: string
  electronic_tag?: string
  name?: string
  birth_date?: string | null
  birth_weight?: number | string | null
  mother_id?: string | null
  father_id?: string | null
  notes?: string | null
}

export type AnimalUpdatePayload = Omit<AnimalWritePayload, 'farm_id' | 'lot_id'> & {
  farm_id: string | null
  lot_id: string | null
}

export interface Species {
  id: string
  code: string
  name: string
  scientific_name?: string | null
}

export interface Breed {
  id: string
  code: string
  name: string
  species_id: string
}

export interface Gender {
  id: string
  code: string
  name: string
}

export interface AnimalStatus {
  id: string
  code: string
  name: string
}

export interface Farm {
  id: string
  name: string
  code: string
  farm_type_id: string
  farm_type: string
  description: string
  address: string
  city: string
  state: string
  country: string
}

export interface Lot {
  id: string
  organization_id: string
  farm_id: string
  code: string
  name: string
  description: string
  capacity: number
}
export interface AnimalParentCandidate {
  id: string
  internal_id: string | null
  name: string | null
  gender_code: string
  is_active: boolean
}
