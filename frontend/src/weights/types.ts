export interface WeightHistory {
  id: string
  date: string
  weight: string
  weighing_method_id: string
}

export interface WeighingMethod {
  id: string
  code: string
  name: string
}

export interface Weight {
  id: string
  animal_id: string
  weighing_method_id: string
  date: string
  weight: string
  notes: string | null
}

export interface WeightCreatePayload {
  animal_id: string
  weighing_method_id: string
  date: string
  weight: number
  notes?: string | null
}