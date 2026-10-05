import type { LoginResponse, User } from './types'

const ACCESS_TOKEN_KEY = 'agrocore.access'
const REFRESH_TOKEN_KEY = 'agrocore.refresh'
const USER_KEY = 'agrocore.user'
const listeners = new Set<() => void>()
let sessionRevision = 0

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function getSessionRevision(): number {
  return sessionRevision
}

function notifySessionChanged(): void {
  sessionRevision += 1
  listeners.forEach((listener) => listener())
}

export interface AuthSession {
  access: string
  refresh: string
  user: User
}

export function saveSession(response: LoginResponse): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, response.access)
  localStorage.setItem(REFRESH_TOKEN_KEY, response.refresh)
  localStorage.setItem(USER_KEY, JSON.stringify(response.user))
  notifySessionChanged()
}

export function getSession(): AuthSession | null {
  const access = localStorage.getItem(ACCESS_TOKEN_KEY)
  const refresh = localStorage.getItem(REFRESH_TOKEN_KEY)
  const storedUser = localStorage.getItem(USER_KEY)

  if (!access || !refresh || !storedUser) {
    return null
  }

  try {
    const user = JSON.parse(storedUser) as User

    return {
      access,
      refresh,
      user,
    }
  } catch {
    // Keep session reads side-effect free for subscribed React routes.
    return null
  }
}

export function clearSession(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  notifySessionChanged()
}

export function invalidateSession(accessToken: string, requestRevision: number): void {
  // Ignore late failures from requests belonging to an earlier login.
  if (requestRevision !== sessionRevision || localStorage.getItem(ACCESS_TOKEN_KEY) !== accessToken) return
  clearSession()
}
