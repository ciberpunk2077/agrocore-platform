import type { LoginResponse, User } from './types'

const ACCESS_TOKEN_KEY = 'agrocore.access'
const REFRESH_TOKEN_KEY = 'agrocore.refresh'
const USER_KEY = 'agrocore.user'

export interface AuthSession {
  access: string
  refresh: string
  user: User
}

export function saveSession(response: LoginResponse): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, response.access)
  localStorage.setItem(REFRESH_TOKEN_KEY, response.refresh)
  localStorage.setItem(USER_KEY, JSON.stringify(response.user))
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
    clearSession()
    return null
  }
}

export function clearSession(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}