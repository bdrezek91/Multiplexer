import { ApiError } from './client'
import { tokenStorage } from './tokenStorage'
import type { CurrentUser } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

// POST /auth/token oczekuje application/x-www-form-urlencoded (OAuth2PasswordRequestForm) -
// osobno od apiRequest(), ktory zawsze wysyla JSON.
export async function login(email: string, password: string): Promise<void> {
  const body = new URLSearchParams({ username: email, password })
  const response = await fetch(`${API_BASE_URL}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  if (!response.ok) {
    let detail = 'Nieprawidlowy email lub haslo'
    try {
      const data = (await response.json()) as { detail?: string }
      if (data.detail) detail = data.detail
    } catch {
      // ignorowane - zostaje domyslny komunikat
    }
    throw new ApiError(response.status, detail)
  }
  const data = (await response.json()) as TokenResponse
  tokenStorage.setTokens(data.access_token, data.refresh_token)
}

export function logout(): void {
  tokenStorage.clear()
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${tokenStorage.getAccessToken() ?? ''}` },
  })
  if (!response.ok) throw new ApiError(response.status, 'Nie udalo sie pobrac danych uzytkownika')
  return (await response.json()) as CurrentUser
}
