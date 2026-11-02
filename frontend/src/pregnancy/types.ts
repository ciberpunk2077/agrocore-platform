export interface PregnancyCreatePayload {
  breeding_id: string
  animal_id: string
  diagnosis_date: string
  expected_birth: string
  confirmed: boolean
  notes?: string | null
}

export interface PregnancyRecord {
  id: string
  breeding_id: string
  animal_id: string
  diagnosis_date: string
  expected_birth: string
  confirmed: boolean
  notes: string | null
  status: string
}

export type PregnancyDetailState =
  | { status: 'idle' }
  | { status: 'loading'; pregnancyId: string }
  | { status: 'success'; pregnancyId: string; record: PregnancyRecord }
  | { status: 'error'; pregnancyId: string; message: string }
