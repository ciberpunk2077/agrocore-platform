import type { AnimalMovementCreatePayload } from './types'

import type { Animal } from '../animals/types'
import type { AnimalMovement } from './types'
export interface DeleteSnapshot {
  revision: number
  organizationId: string
  movement: Readonly<AnimalMovement>
  animal: Readonly<Animal>
  history: readonly Readonly<AnimalMovement>[]
}
export type CreatePhase = 'idle' | 'pending' | 'confirmed' | 'uncertain'
export interface Attempt {
  phase: Exclude<CreatePhase, 'idle'>
  payload: Readonly<AnimalMovementCreatePayload>
  kind: 'create' | 'update' | 'delete'
  movementId?: string
  originStatusId?: string | null
  deleteSnapshot?: Readonly<DeleteSnapshot>
  reconciled?: boolean
}
// Preserve unresolved attempts across A → B → A within the same session/context.
// Never infer ownership of a history record from payload equivalence.
const attempts = new Map<string, Attempt>()
export function attemptKey(revision: number, organizationId: string, animalId: string) {
  return `${revision}:${organizationId}:${animalId}`
}
export const getAttempt = (key: string) => attempts.get(key)
export function beginAttempt(key: string, payload: AnimalMovementCreatePayload, update?: { movementId: string; originStatusId: string | null }): boolean {
  if (attempts.has(key)) return false
  attempts.set(key, { phase: 'pending', payload: Object.freeze({ ...payload }), kind: update ? 'update' : 'create', ...update })
  return true
}
export function setAttemptPhase(key: string, phase: 'confirmed' | 'uncertain') {
  const attempt = attempts.get(key)
  if (attempt) attempt.phase = phase
}
export const finishAttempt = (key: string) => { attempts.delete(key) }
export function abandonPending(key: string) {
  if (attempts.get(key)?.phase === 'pending') setAttemptPhase(key, 'uncertain')
}
export function beginDeleteAttempt(key: string, snapshot: DeleteSnapshot): boolean {
  if (attempts.has(key)) return false
  const movement = Object.freeze({ ...snapshot.movement })
  const immutable = Object.freeze({ ...snapshot, movement, animal: Object.freeze({ ...snapshot.animal }),
    history: Object.freeze(snapshot.history.map(m => Object.freeze({ ...m }))) })
  attempts.set(key, { phase: 'pending', kind: 'delete', movementId: movement.id,
    originStatusId: movement.origin_status_id, payload: movement, deleteSnapshot: immutable })
  return true
}
export function reconcileDeletion(key: string) {
  const attempt = attempts.get(key)
  if (attempt?.kind === 'delete') { attempt.phase = 'confirmed'; attempt.reconciled = true }
}
