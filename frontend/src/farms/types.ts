export type { Farm } from '../animals/types'

export interface FarmType {
  id: string
  code: string
  name: string
  description: string | null
}

export interface FarmCreatePayload {
  name: string
  code: string
  farm_type_id: string
  description: string
  address: string
  city: string
  state: string
  country: string
}

export type FarmUpdatePayload = FarmCreatePayload
