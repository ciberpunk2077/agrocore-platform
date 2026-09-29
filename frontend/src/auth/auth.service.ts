import { apiRequest } from '../lib/api'
import type { LoginCredentials, LoginResponse, User } from './types'

export function login(credentials: LoginCredentials): Promise<LoginResponse> {
  return apiRequest<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
}

export function getCurrentUser(accessToken: string): Promise<User> {
  return apiRequest<User>('/auth/me', {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}