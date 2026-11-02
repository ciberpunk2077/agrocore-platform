import type { PregnancyRecord } from './types'
export type AbortPhase = 'idle' | 'preparing' | 'pending' | 'confirmed' | 'uncertain'
export interface AbortTarget {
  pregnancyId: string; animalId: string; breedingId: string; revision: number; organizationId: string
}
interface AbortAttempt {
  phase: Exclude<AbortPhase, 'idle'>; target: Readonly<AbortTarget>; localRevision: number
  fresh?: Readonly<PregnancyRecord>
}
// Memory only: navigation retains unresolved targets; F5/other tabs do not.
const attempts = new Map<string, AbortAttempt>()
export const getAbortAttempt = (scope: string) => attempts.get(scope)
export function beginAbort(scope: string, target: AbortTarget, localRevision: number) {
  if (attempts.has(scope)) return false
  attempts.set(scope, { phase: 'preparing', target: Object.freeze({ ...target }), localRevision })
  return true
}
export function setAbortPhase(scope: string, phase: Exclude<AbortPhase, 'idle'>) {
  const attempt = attempts.get(scope)
  if (attempt) attempt.phase = phase
}
export function prepareAbort(scope: string, fresh: PregnancyRecord) {
  const attempt = attempts.get(scope)
  if (attempt) attempt.fresh = Object.freeze({ ...fresh })
}
export const finishAbort = (scope: string) => { attempts.delete(scope) }
export function abandonAbort(scope: string) {
  const attempt = attempts.get(scope)
  if (attempt?.phase === 'preparing') finishAbort(scope)
  else if (attempt?.phase === 'pending') attempt.phase = 'uncertain'
}
