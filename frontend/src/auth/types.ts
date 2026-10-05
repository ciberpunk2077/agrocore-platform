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

export interface CurrentContext {
  user: string
  current_user: User
  organization: { id: string; name: string; code: string } | null
  membership: { id: string; is_default: boolean } | null
  role: MembershipRole | null
  can_read: boolean
  can_write: boolean
}
