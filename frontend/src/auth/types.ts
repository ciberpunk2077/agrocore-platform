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