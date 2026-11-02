import { getSessionRevision, invalidateSession } from '../auth/session'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? '/api'

export class ApiError extends Error {
  status: number
  data: unknown

  constructor(status: number, data: unknown) {
    super(`API request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

interface ApiRequestOptions extends RequestInit {
  accessToken?: string
  expectedStatus?: number
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { accessToken, expectedStatus, ...requestOptions } = options
  if (typeof __AGROCORE_DEMO__ !== 'undefined' && __AGROCORE_DEMO__) {
    const method = (requestOptions.method ?? 'GET').toUpperCase()
    if (API_BASE_URL !== '/api' || !path.startsWith('/') || path.startsWith('//') || path.includes('\\') ||
      (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !(method === 'POST' && path === '/auth/login'))) {
      throw new Error('Demostraci?n de solo lectura: solicitud bloqueada antes de enviarse.')
    }
    requestOptions.cache = 'no-store'
  }
  const requestRevision = getSessionRevision()
  const headers = new Headers(requestOptions.headers)

  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)

  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...requestOptions,
    headers,
  })

  if (response.status === 401 && accessToken) {
    invalidateSession(accessToken, requestRevision)
  }

  const data: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    throw new ApiError(response.status, data)
  }

  if (expectedStatus !== undefined && response.status !== expectedStatus) {
    throw new Error('Respuesta HTTP inesperada; resultado no confirmado.')
  }

  return data as T
}
