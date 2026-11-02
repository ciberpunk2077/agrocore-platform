import { apiRequest } from '../lib/api'
import type { ResolvedCurrentContext, LoginCredentials, LoginResponse } from './types'
import { parseCurrentContext } from './current-context-validation'
import { createBusinessTimeLease } from './business-time'

export async function getCurrentContext(accessToken: string, signal?: AbortSignal): Promise<ResolvedCurrentContext> {
  const started = performance.now(), wall = Date.now()
  const data = parseCurrentContext(await apiRequest<unknown>('/common/context', {
    accessToken,
    signal,
    cache: 'no-store', expectedStatus: 200,
  }))
  return { ...data, businessTimeLease: createBusinessTimeLease(data.business_time, started, wall) }
}

export function login(credentials: LoginCredentials): Promise<LoginResponse> {
  return apiRequest<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
}

