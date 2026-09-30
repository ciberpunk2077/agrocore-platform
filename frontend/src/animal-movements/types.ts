export interface MovementType {
  id: string
  code: string
  name: string
}

export interface AnimalMovementCreatePayload {
  animal_id: string
  movement_type_id: string
  origin_farm_id?: string | null
  origin_lot_id?: string | null
  destination_farm_id?: string | null
  destination_lot_id?: string | null
  date: string
  reason?: string | null
  notes?: string | null
}

export interface AnimalMovement {
  id: string
  animal_id: string
  movement_type_id: string
  origin_status_id: string | null
  origin_farm_id: string | null
  origin_lot_id: string | null
  destination_farm_id: string | null
  destination_lot_id: string | null
  date: string
  reason: string | null
  notes: string | null
}
