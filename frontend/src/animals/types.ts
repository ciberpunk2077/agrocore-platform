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

  notes: string | null
  is_active: boolean
}