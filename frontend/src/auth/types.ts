export interface User {
  id: string
  email: string
  first_name: string
  last_name: string
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface LoginResponse {
  access: string
  refresh: string
  user: User
}

export type MembershipRole = 'OWNER' | 'ADMIN' | 'VETERINARIAN' | 'OPERATOR' | 'VIEWER'

export interface BusinessTime {
  effective_timezone: string
  business_today: string
  server_now: string
  valid_until: string
}

export interface BusinessTimeLease {
  snapshot: BusinessTime
  receivedMonotonic: number
  receivedWall: number
  remainingMs: number
}

export interface CurrentContext {
  user: string
  current_user: User
  organization: { id: string; name: string; code: string } | null
  membership: { id: string; is_default: boolean } | null
  role: MembershipRole | null
  can_read: boolean
  can_write: boolean
  business_time: BusinessTime | null
}

export interface ResolvedCurrentContext extends CurrentContext {
  businessTimeLease: BusinessTimeLease | null
}
