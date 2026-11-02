import type { PreparedPayload } from './validation'
export type CreatePhase = 'idle' | 'preparing' | 'pending' | 'confirmed' | 'uncertain'
interface Attempt {
  phase: Exclude<CreatePhase, 'idle'>
  target: Readonly<PreparedPayload>
  payload: Readonly<PreparedPayload> | null
}
// The frozen target includes Pregnancy/calf/gender. An unresolved attempt blocks
// all writes for this mother. Hard reload and other tabs have separate memory.
const attempts = new Map<string, Attempt>()
export const attemptKey = (revision: number, organization: string, mother: string) => `${revision}:${organization}:${mother}`
export const getAttempt = (key: string) => attempts.get(key)
export function beginPreparation(key: string, target: PreparedPayload) {
  if (attempts.has(key)) return null
  const attempt: Attempt = { phase: 'preparing', target: Object.freeze({ ...target }), payload: null }
  attempts.set(key, attempt)
  return attempt
}
export function preparePayload(key: string, payload: PreparedPayload) {
  const attempt = attempts.get(key)
  if (attempt?.phase === 'preparing') attempt.payload = Object.freeze({ ...payload })
}
export function setAttemptPhase(key: string, phase: Exclude<CreatePhase, 'idle'>) {
  const attempt = attempts.get(key)
  if (attempt) attempt.phase = phase
}
export const finishAttempt = (key: string) => { attempts.delete(key) }
export function abandonScope(key: string) {
  const attempt = attempts.get(key)
  if (attempt?.phase === 'preparing') finishAttempt(key)
  else if (attempt?.phase === 'pending') attempt.phase = 'uncertain'
}
