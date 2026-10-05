export type { Lot } from '../animals/types'

export interface LotCreatePayload {
  farm_id: string
  code: string
  name: string
  description: string
  capacity: number
}

export type LotUpdatePayload = LotCreatePayload
