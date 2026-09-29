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