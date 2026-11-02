import type { BusinessTime, BusinessTimeLease } from './types'

export function createBusinessTimeLease(snapshot: BusinessTime | null, requestMonotonic: number, requestWall: number): BusinessTimeLease | null {
  if (!snapshot) return null
  const receivedMonotonic = performance.now(), receivedWall = Date.now()
  // Subtract the entire round trip, rather than trusting the browser's clock.
  const roundTrip = Math.max(0, receivedMonotonic - requestMonotonic, receivedWall - requestWall)
  // JS truncates Django's microseconds; reserve a millisecond so that rounding
  // cannot extend a lease beyond a civil-day boundary.
  const remainingMs = Date.parse(snapshot.valid_until) - Date.parse(snapshot.server_now) - roundTrip - 1
  return remainingMs > 0 ? { snapshot, receivedMonotonic, receivedWall, remainingMs } : null
}

export function businessTimeRemaining(lease: BusinessTimeLease | null): number {
  if (!lease) return 0
  const elapsed = Math.max(0, performance.now() - lease.receivedMonotonic, Date.now() - lease.receivedWall)
  return Math.max(0, lease.remainingMs - elapsed)
}

export const businessTimeIsFresh = (lease: BusinessTimeLease | null) => businessTimeRemaining(lease) > 0
