export interface ProductionRecord {
  id: string
  animal_id: string
  production_type_id: string
  recorded_at: string
  quantity: string
  unit: string
  notes: string
  is_active: boolean
}

export interface ProductionType {
  id: string
  code: string
  name: string
  default_unit: string
  description: string
}

export interface ProductionCreatePayload {
  animal_id: string
  production_type_id: string
  recorded_at: string
  quantity: string
  notes: string
}

export type ProductionUpdatePayload = ProductionCreatePayload
