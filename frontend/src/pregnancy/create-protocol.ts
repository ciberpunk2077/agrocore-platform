import type { PreparedPayload } from './validation'

export type CreatePhase = 'idle' | 'preparing' | 'pending' | 'confirmed' | 'uncertain'
interface Attempt {
  phase: Exclude<CreatePhase, 'idle'>
  payload: Readonly<PreparedPayload>
  localRevision: number
}
// In-memory scope: navigation keeps unresolved writes; hard reload/other tabs do not.
const attempts = new Map<string, Attempt>()
export const attemptKey = (revision: number, organizationId: string, animalId: string) => `${revision}:${organizationId}:${animalId}`
export const getAttempt = (key: string) => attempts.get(key)
export function beginPreparation(key: string, payload: PreparedPayload, localRevision: number) {
  if (attempts.has(key)) return false
  attempts.set(key, { phase: 'preparing', payload: Object.freeze({ ...payload }), localRevision })
  return true
}
export function setAttemptPhase(key: string, phase: Exclude<CreatePhase, 'idle'>) {
  const attempt = attempts.get(key)
  if (attempt) attempt.phase = phase
}
export const finishAttempt = (key: string) => { attempts.delete(key) }
export function abandonScope(key: string) {
  const attempt = attempts.get(key)
  if (attempt?.phase === 'preparing') finishAttempt(key) // No POST was sent.
  else if (attempt?.phase === 'pending') attempt.phase = 'uncertain'
}
