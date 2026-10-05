import { apiRequest } from '../lib/api'
import type { CurrentContext, LoginCredentials, LoginResponse } from './types'

export function getCurrentContext(accessToken: string, signal?: AbortSignal): Promise<CurrentContext> {
  return apiRequest<CurrentContext>('/common/context', {
    accessToken,
    signal,
  })
}

export function login(credentials: LoginCredentials): Promise<LoginResponse> {
  return apiRequest<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
}

